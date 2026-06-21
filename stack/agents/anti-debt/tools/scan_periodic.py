#!/usr/bin/env python3
"""scan_periodic.py — Layer 4: Multi-project orchestrator with scheduling.

Scans multiple projects on a schedule, deduplicates findings via the KG,
and triggers alerts on critical findings.

Usage:
    python3 scan_periodic.py --config projects.json
    python3 scan_periodic.py --config projects.json --once
    python3 scan_periodic.py --config projects.json --interval 3600   # loop, 1h tick

Config (projects.json):
    [
      {
        "name": "seno-daw",
        "path": "D:/App/Seno",
        "enabled": true,
        "scan_layers": [0, 1, 3],     # which layers to run
        "alert": {"critical": "telegram", "high": "telegram"},
        "ignore_paths": ["build", "target", "node_modules"]
      },
      ...
    ]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent  # agents/anti-debt/
KG_TOOLS = ROOT / "kg"
STATIC_TOOLS = ROOT / "tools"
SCAN_TOOLS = ROOT / "skills" / "debt-scan" / "tools"
KG_DB = ROOT / "kg" / "data" / "kg.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alert_telegram(message: str, bot_token: str | None = None, chat_id: str | None = None) -> bool:
    """Send a Telegram message via bot API. Best-effort.

    Token/chat_id can be passed explicitly or read from env (TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID). Returns True if sent, False otherwise.
    """
    try:
        import urllib.request
        import urllib.parse
    except ImportError:
        return False
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat, "text": message, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, timeout=10)
        with urllib.request.urlopen(req) as r:
            return r.status == 200
    except Exception:
        return False


def _alert_log(message: str, alert_log_path: Path) -> None:
    """Append to a local alert log (always available fallback)."""
    with alert_log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{_now()}] {message}\n")


def _run_layer_scan(project_path: Path, scan_layers: list[int]) -> dict:
    """Run the requested scan layers on a project.

    Returns {"findings": [...], "scanners": [...]}.
    """
    findings: list = []
    scanners: list = []
    # Layer 0: storage (KG migration / sync) — handled separately
    # Layer 1: static analysis
    if 1 in scan_layers:
        result = subprocess.run(
            [sys.executable, str(STATIC_TOOLS / "static_analysis.py"), str(project_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
        )
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                findings.extend(data.get("findings", []))
                scanners.append("static_analysis")
            except json.JSONDecodeError:
                pass
    # Layer 3: debt-scan — the FULL skill scans all categories (code + security
    # + dependencies), not just code. Running scan_code alone would silently
    # narrow the scope (the very MVP bias the agent exists to prevent).
    if 3 in scan_layers:
        for script in ("scan_code.py", "scan_security.py", "scan_deps.py"):
            result = subprocess.run(
                [sys.executable, str(SCAN_TOOLS / script), str(project_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            )
            if not result.stdout.strip():
                continue
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                continue
            findings.extend([f for f in data.get("findings", [])
                              if "category" in f and "subcategory" in f])
            scanners.append(script[:-3])
    return {"findings": findings, "scanners": scanners}


def _store_in_kg(project_name: str, project_path: str, findings: list) -> dict:
    """Persist findings into the KG as Component + Debt nodes.

    Returns counts: {components, debts, edges}.
    """
    KG_DB.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(KG_TOOLS))
    sys.path.insert(0, str(STATIC_TOOLS))
    from kg_schema import init_kg  # type: ignore
    from kg_store import KgStore  # type: ignore
    from kg_query import KgQuery  # type: ignore
    from kg_schema import Node, Edge  # type: ignore
    from finding_common import finding_id  # type: ignore

    init_kg(KG_DB)
    counts = {"components": 0, "debts": 0, "edges": 0}
    with KgStore(KG_DB) as store:
        # Upsert a Component for the project
        comp_id = f"component-{project_name}"
        comp_node = Node(
            id=comp_id, type="Component",
            name=project_name,
            metadata={"path": project_path, "scanned_at": _now()},
        )
        store.upsert_node(comp_node)
        counts["components"] += 1
        # Upsert a Debt node for each finding
        for f in findings:
            if "warning" in f:
                continue
            # Fallback id is deterministic (never random) so the same physical
            # debt keeps one KG node across scans, even if a scanner omitted id.
            debt_id = f.get("id") or finding_id(
                f.get("category", ""), f.get("subcategory", ""),
                f.get("location", {}).get("file", ""),
                str(f.get("location", {}).get("lines", "")),
            )
            debt_node = Node(
                id=debt_id, type="Debt",
                name=f.get("description", "?")[:80],
                metadata={
                    "category": f.get("category"),
                    "subcategory": f.get("subcategory"),
                    "severity": f.get("severity"),
                    "file": f.get("location", {}).get("file", ""),
                    "line": f.get("location", {}).get("lines", ""),
                    "source": f.get("source", ""),
                    "first_seen": f.get("first_seen", _now()),
                },
            )
            store.upsert_node(debt_node)
            counts["debts"] += 1
            # Edge: Debt affects Component
            edge = Edge(
                id=f"edge-{debt_id}-affects-{comp_id}",
                source_id=debt_id, target_id=comp_id, type="affects",
                metadata={"detected_at": _now()},
            )
            store.upsert_edge(edge)
            counts["edges"] += 1
    return counts


def _format_alert(project_name: str, findings: list) -> str:
    """Format a short alert message for critical/high findings."""
    crit = [f for f in findings if f.get("severity") == "critical"]
    high = [f for f in findings if f.get("severity") == "high"]
    if not crit and not high:
        return ""
    lines = [f"<b>Anti-debt alert: {project_name}</b>"]
    if crit:
        lines.append(f"🔴 {len(crit)} critical:")
        for f in crit[:5]:
            lines.append(f"  - {f.get('subcategory', '?')}: {f.get('description', '?')[:60]}")
    if high:
        lines.append(f"🟠 {len(high)} high")
    return "\n".join(lines)


def scan_project(project: dict) -> dict:
    """Scan a single project according to its config."""
    name = project.get("name", "?")
    path = Path(project.get("path", "."))
    if not path.is_dir():
        return {"project": name, "error": f"path not found: {path}"}
    layers = project.get("scan_layers", [1, 3])
    alert_cfg = project.get("alert", {})
    # Scan
    result = _run_layer_scan(path, layers)
    findings = result["findings"]
    # Persist to KG
    kg_counts = {}
    try:
        kg_counts = _store_in_kg(name, str(path), findings)
    except Exception as e:
        kg_counts = {"error": str(e)}
    # Alerts
    alerts_sent = []
    if alert_cfg:
        msg = _format_alert(name, findings)
        if msg:
            for sev, target in alert_cfg.items():
                if sev in ("critical", "high") and target == "telegram":
                    ok = _alert_telegram(msg)
                    alerts_sent.append({"target": "telegram", "severity": sev, "sent": ok})
                elif target == "log":
                    _alert_log(msg, ROOT / "alerts.log")
                    alerts_sent.append({"target": "log", "severity": sev, "sent": True})
    return {
        "project": name,
        "path": str(path),
        "scanners": result["scanners"],
        "findings_count": len(findings),
        "by_severity": {
            "critical": sum(1 for f in findings if f.get("severity") == "critical"),
            "high": sum(1 for f in findings if f.get("severity") == "high"),
            "medium": sum(1 for f in findings if f.get("severity") == "medium"),
            "low": sum(1 for f in findings if f.get("severity") == "low"),
        },
        "kg": kg_counts,
        "alerts": alerts_sent,
        "scanned_at": _now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Anti-debt multi-project orchestrator")
    parser.add_argument("--config", required=True, help="Path to projects.json config")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=3600, help="Loop interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Skip KG persistence and alerts")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(json.dumps({"error": f"config not found: {config_path}"}))
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8"))
    projects = config.get("projects") if isinstance(config, dict) else config
    if not isinstance(projects, list):
        print(json.dumps({"error": "config must be a list of projects, or a dict with 'projects' key"}))
        return 1

    print(f"[{_now()}] scan_periodic starting ({len(projects)} projects, dry_run={args.dry_run})")
    while True:
        results = []
        for project in projects:
            if not project.get("enabled", True):
                continue
            try:
                r = scan_project(project)
                results.append(r)
                summary = f"{r['project']}: {r.get('findings_count', 0)} findings " \
                          f"(critical={r.get('by_severity', {}).get('critical', 0)}, " \
                          f"high={r.get('by_severity', {}).get('high', 0)})"
                print(f"[{_now()}] {summary}")
            except Exception as e:
                results.append({"project": project.get("name", "?"), "error": str(e)})
                print(f"[{_now()}] ERROR on {project.get('name', '?')}: {e}")
        # Summary
        report_path = ROOT / "tools" / "scan_periodic_report.json"
        report_path.write_text(json.dumps({
            "last_run": _now(),
            "results": results,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.once:
            return 0
        print(f"[{_now()}] sleeping {args.interval}s until next run")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
