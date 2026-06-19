#!/usr/bin/env python3
"""scan_security.py — Detect secrets + known vulnerabilities.

Runs trufflehog (or gitleaks) + osv-scanner, normalizes to debt-finding schema.

Usage:
    python3 scan_security.py [path-to-repo]
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id  # noqa: E402


TOOLS = [
    {
        "name": "trufflehog",
        "cmd": ["trufflehog", "filesystem", ".", "--json"],
        "parser": "trufflehog",
        "installed_check": ["trufflehog", "--version"],
    },
    {
        "name": "gitleaks",
        "cmd": ["gitleaks", "detect", "--source", ".", "--report-format", "json", "--no-git"],
        "parser": "gitleaks",
        "installed_check": ["gitleaks", "version"],
    },
    {
        "name": "osv-scanner",
        "cmd": ["osv-scanner", "-r", ".", "--format", "json"],
        "parser": "osv-scanner",
        "installed_check": ["osv-scanner", "--version"],
    },
]


def normalize_trufflehog(stdout: str) -> list[dict]:
    """Convert trufflehog JSONL output to debt-finding schema."""
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if item.get("Verified") is True:
            severity = "critical"
            confidence = 0.99
        else:
            severity = "high"
            confidence = 0.85

        source_path = item.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {}).get("file", "")
        raw = item.get("Raw", "")
        # Truncate raw secret to first 8 chars to avoid leaking in reports
        raw_preview = raw[:8] + "..." if len(raw) > 8 else raw

        findings.append({
            "id": finding_id("security", "secrets_in_code", source_path, "",
                             f"trufflehog:{item.get('DetectorName', '?')}:{raw_preview}"),
            "category": "security",
            "subcategory": "secrets_in_code",
            "severity": severity,
            "location": {"file": source_path},
            "description": f"Secret detected by trufflehog: {item.get('DetectorName', 'unknown')} ({'verified' if item.get('Verified') else 'unverified'})",
            "evidence": [
                {"type": "file_location", "value": source_path},
                {"type": "tool_output", "tool": "trufflehog", "value": f"Detector {item.get('DetectorName', '?')} verified={item.get('Verified')}, preview={raw_preview}"},
            ],
            "confidence": confidence,
            "source": "tool:trufflehog",
            "estimated_effort": "S",
            "risk_of_fix": "low",
            "auto_fixable": False,
            "first_seen": now,
            "last_seen": now,
        })
    return findings


def normalize_gitleaks(stdout: str) -> list[dict]:
    """Convert gitleaks JSON output to debt-finding schema."""
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    if not stdout.strip():
        return findings
    try:
        items = json.loads(stdout)
    except json.JSONDecodeError:
        return findings

    if isinstance(items, dict):
        items = [items]

    for item in items:
        findings.append({
            "id": finding_id("security", "secrets_in_code", item.get("File", ""),
                             str(item.get("StartLine", "?")), item.get("RuleID", "")),
            "category": "security",
            "subcategory": "secrets_in_code",
            "severity": "critical",
            "location": {"file": item.get("File", ""), "lines": str(item.get("StartLine", "?"))},
            "description": f"Secret detected by gitleaks: {item.get('RuleID', 'unknown')}",
            "evidence": [
                {"type": "file_location", "value": f"{item.get('File', '')}:{item.get('StartLine', '?')}"},
                {"type": "tool_output", "tool": "gitleaks", "value": f"Rule {item.get('RuleID', '?')} secret (preview {item.get('Secret', '')[:8]}...)"},
            ],
            "confidence": 0.95,
            "source": "tool:gitleaks",
            "estimated_effort": "S",
            "risk_of_fix": "low",
            "auto_fixable": False,
            "first_seen": now,
            "last_seen": now,
        })
    return findings


def normalize_osv(stdout: str) -> list[dict]:
    """Convert osv-scanner JSON output to debt-finding schema."""
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return findings

    results = data.get("results", [])
    for result in results:
        source_path = result.get("source", {}).get("path", "")
        for pkg in result.get("packages", []):
            pkg_info = pkg.get("package", {})
            pkg_name = pkg_info.get("name", "?")
            pkg_version = pkg_info.get("version", "?")
            for vuln in pkg.get("vulnerabilities", []):
                vuln_id = vuln.get("id", "?")
                summary = vuln.get("summary", "")
                severity = "high"
                db_severity = vuln.get("severity", [])
                for s in db_severity:
                    s_type = s.get("type", "")
                    s_score = s.get("score", "")
                    if s_type == "CVSS_V3" and s_score:
                        try:
                            score = float(s_score.split("/")[-1]) if "/" in s_score else float(s_score)
                            if score >= 9.0:
                                severity = "critical"
                            elif score >= 7.0:
                                severity = "high"
                            elif score >= 4.0:
                                severity = "medium"
                            else:
                                severity = "low"
                        except (ValueError, IndexError):
                            pass

                findings.append({
                    "id": finding_id("security", "known_vulns", source_path or "dependencies",
                                     "", f"{pkg_name}@{pkg_version}:{vuln_id}"),
                    "category": "security",
                    "subcategory": "known_vulns",
                    "severity": severity,
                    "location": {"file": source_path or "dependencies", "symbol": f"{pkg_name}@{pkg_version}"},
                    "description": f"{vuln_id}: {summary[:200]}",
                    "evidence": [
                        {"type": "tool_output", "tool": "osv-scanner", "value": f"{pkg_name}@{pkg_version} vulnerable to {vuln_id}"},
                    ],
                    "confidence": 1.0,
                    "source": "tool:osv-scanner",
                    "estimated_effort": "M",
                    "risk_of_fix": "medium",
                    "auto_fixable": False,
                    "first_seen": now,
                    "last_seen": now,
                })
    return findings


PARSERS = {
    "trufflehog": normalize_trufflehog,
    "gitleaks": normalize_gitleaks,
    "osv-scanner": normalize_osv,
}


def is_installed(check_cmd: list[str]) -> bool:
    try:
        result = subprocess.run(check_cmd, capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 1

    all_findings = []
    installed_tools = []
    warnings = []

    for tool in TOOLS:
        if not is_installed(tool["installed_check"]):
            warnings.append({
                "warning": f"tool:{tool['name']} not installed",
                "recommendation": f"install {tool['name']} for better coverage",
            })
            continue

        installed_tools.append(tool["name"])
        try:
            result = subprocess.run(
                tool["cmd"],
                capture_output=True,
                text=True,
                cwd=str(root),
                timeout=600,
            )
            # trufflehog exits 0 even when secrets found; osv-scanner exits 1
            if result.returncode not in (0, 1):
                warnings.append({"warning": f"{tool['name']} exited {result.returncode}", "stderr_tail": result.stderr[-300:]})
                continue
            findings = PARSERS[tool["parser"]](result.stdout)
            all_findings.extend(findings)
        except subprocess.TimeoutExpired:
            warnings.append({"warning": f"{tool['name']} timed out after 600s"})
        except Exception as e:
            warnings.append({"warning": f"{tool['name']} failed: {type(e).__name__}: {e}"})

    print(json.dumps({
        "tools_installed": installed_tools,
        "tools_missing": [t["name"] for t in TOOLS if t["name"] not in installed_tools],
        "warnings": warnings,
        "findings": all_findings,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
