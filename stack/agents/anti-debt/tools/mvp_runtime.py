#!/usr/bin/env python3
"""mvp_runtime.py — Mode MVP runtime: scan -> plan -> human confirm -> dry-run fix.

End-to-end orchestration of the anti-debt agent for one project. Skips
the actual fix application (which requires an LLM) but produces a complete
plan + dry-run + human confirmation flow.

Pipeline:
1. Scan the project (Layer 1 static analysis + Layer 3 debt-scan)
2. Apply Critic V2 (tier filter + score)
3. Build a debt plan with critic_validation block
4. Show top 5 P0/P1 findings and ask for human confirmation
5. (If confirmed) Print the patch commands; do NOT apply

Usage:
    python3 mvp_runtime.py [path-to-project]
    python3 mvp_runtime.py [path-to-project] --auto-confirm   # CI mode
    python3 mvp_runtime.py [path-to-project] --output plan.json
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOOLS = ROOT / "tools"
STATIC = TOOLS / "static_analysis.py"
CRITIC = TOOLS / "critic_v2.py"
SCAN_DIR = ROOT / "skills" / "debt-scan" / "tools"
SCAN_CODE = SCAN_DIR / "scan_code.py"

# Directive 1 (anti-MVP): a "complete plan" must scan ALL applicable categories,
# not just `code`. Each scanner declares which taxonomy categories it covers.
SCANNERS = [
    (STATIC, ("code",)),
    (SCAN_CODE, ("code",)),
    (SCAN_DIR / "scan_security.py", ("security",)),
    (SCAN_DIR / "scan_deps.py", ("security", "dependencies")),
]

# Taxonomy categories with no deterministic scanner in V1 — declared explicitly
# rather than silently dropped (Directive 6: scope completeness check).
UNSCANNED_CATEGORIES = {
    "tests": "no deterministic scanner wired in V1 (coverage tooling pending)",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_scanners(project_path: Path) -> tuple[list[dict], list[dict]]:
    """Run all category scanners, merge findings, dedupe by id.

    Returns (findings, scan_meta). scan_meta records, per scanner, whether it
    ran, how many findings it produced, and any error/warnings — so the caller
    can declare real category coverage instead of assuming completeness.
    """
    findings_by_id: dict = {}
    scan_meta: list[dict] = []
    for script, categories in SCANNERS:
        meta = {"scanner": script.name, "categories": list(categories),
                "ran": False, "n_findings": 0, "warnings": [], "error": None}
        if not script.exists():
            meta["error"] = "scanner script not found"
            scan_meta.append(meta)
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(script), str(project_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            meta["error"] = str(e)
            print(f"  WARN: {script.name} failed: {e}", file=sys.stderr)
            scan_meta.append(meta)
            continue
        if not proc.stdout.strip():
            meta["error"] = "empty output"
            scan_meta.append(meta)
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            meta["error"] = "invalid JSON output"
            scan_meta.append(meta)
            continue
        if isinstance(data, dict) and data.get("error"):
            # e.g. scan_code -> {"error": "no_supported_language"}: not fatal,
            # but the scanner produced no coverage for its category.
            meta["error"] = data["error"]
            scan_meta.append(meta)
            continue
        meta["ran"] = True
        meta["warnings"] = data.get("warnings", []) if isinstance(data, dict) else []
        n = 0
        for f in data.get("findings", []):
            if not isinstance(f, dict) or "category" not in f:
                continue
            fid = f.get("id") or f"f-{hash(str(f))}"
            # Keep the first occurrence (lowest ID) for dedup
            if fid not in findings_by_id:
                findings_by_id[fid] = f
                n += 1
        meta["n_findings"] = n
        scan_meta.append(meta)
    return list(findings_by_id.values()), scan_meta


def _scope_completeness(scan_meta: list[dict]) -> dict:
    """Derive category coverage + plan completeness from scanner results.

    A plan is 'complete' only when every scannable category actually had a
    scanner run successfully. Categories with no V1 tooling are declared, not
    silently dropped (Directive 6).
    """
    scannable = {c for _, cats in SCANNERS for c in cats}
    covered = {c for m in scan_meta if m["ran"] for c in m["categories"]}
    missing = sorted(scannable - covered)
    complete = not missing
    return {
        "categories_covered": sorted(covered),
        "categories_missing_tooling": missing,
        "categories_no_scanner": dict(UNSCANNED_CATEGORIES),
        "plan_completeness": "complete" if complete else "partial",
    }


def _apply_critic(findings: list) -> dict:
    """Apply Critic V2 by piping findings through its score subcommand."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(findings, f)
        findings_path = f.name
    plan_path = findings_path + ".plan.json"
    try:
        proc = subprocess.run(
            [sys.executable, str(CRITIC), "score", findings_path, plan_path],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if proc.returncode != 0:
            return {"error": proc.stderr or "critic_v2 failed", "fix_order": [], "review": [], "rejected": []}
        return json.loads(Path(plan_path).read_text(encoding="utf-8"))
    finally:
        Path(findings_path).unlink(missing_ok=True)
        Path(plan_path).unlink(missing_ok=True)


def _format_top(plan: dict, n: int = 5) -> str:
    """Format the top N findings for human review."""
    lines = []
    accepted = plan.get("fix_order", [])
    for i, f in enumerate(accepted[:n], start=1):
        sev = f.get("severity", "?").upper()
        score = f.get("score", 0.0)
        sub = f.get("subcategory", "?")
        loc = f.get("location", {}).get("file", "?")
        line = f.get("location", {}).get("lines", "?")
        desc = f.get("description", "?")[:80]
        lines.append(f"  {i}. [{sev}] score={score} {sub} @ {loc}:{line}")
        lines.append(f"     {desc}")
    if not lines:
        lines.append("  (no P0/P1 findings — clean project or all in 'review' tier)")
    return "\n".join(lines)


def _print_plan_summary(plan: dict, project_path: Path) -> None:
    cv = plan.get("critic_validation", {})
    print(f"\n=== Plan for {project_path} ===")
    print(f"  Project: {plan.get('project', '?')}")
    print(f"  Created: {plan.get('created_at', '?')}")
    print(f"  Engine: {cv.get('engine_version', '?')}")
    tc = cv.get("tier_counts", {})
    print(f"  Tiers:  accepted={tc.get('accepted', 0)}  review={tc.get('review', 0)}  rejected={tc.get('rejected', 0)}")
    print(f"\n  Top findings to fix:")
    print(_format_top(plan))


def _print_scope(scope: dict) -> None:
    """Print the scope completeness check (Directive 6)."""
    print("\n  Scope completeness check:")
    print(f"    Plan completeness : {scope['plan_completeness'].upper()}")
    print(f"    Covered           : {', '.join(scope['categories_covered']) or '(none)'}")
    if scope["categories_missing_tooling"]:
        print(f"    Missing tooling   : {', '.join(scope['categories_missing_tooling'])} "
              f"(scanner present but tool not installed / no supported language)")
    for cat, reason in scope["categories_no_scanner"].items():
        print(f"    Not scanned       : {cat} — {reason}")


def _confirm_human(plan: dict) -> bool:
    """Ask the human for confirmation. Returns True if confirmed."""
    accepted = plan.get("fix_order", [])
    if not accepted:
        return True  # nothing to fix, no need to confirm
    print(f"\n  Plan contains {len(accepted)} findings to fix.")
    try:
        resp = input("  Apply these fixes? [y/N/dry-run]: ").strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")


def _dry_run(plan: dict) -> list[str]:
    """Generate a list of patch commands. Do NOT apply them."""
    cmds = []
    for f in plan.get("fix_order", []):
        loc = f.get("location", {}).get("file", "?")
        line = f.get("location", {}).get("lines", "?")
        sub = f.get("subcategory", "?")
        # The actual fix requires an LLM. We print a placeholder.
        cmds.append(f"# Fix {sub} at {loc}:{line}  -> requires LLM (use /skill debt-fix)")
    return cmds


def main() -> int:
    parser = argparse.ArgumentParser(description="Mode MVP runtime orchestrator")
    parser.add_argument("project", help="Path to project to scan")
    parser.add_argument("--output", default=None, help="Write plan to this JSON file")
    parser.add_argument("--auto-confirm", action="store_true", help="Skip human confirmation (CI mode)")
    parser.add_argument("--dry-run-only", action="store_true", help="Print dry-run commands instead of running them")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.is_dir():
        print(json.dumps({"error": f"not a directory: {project_path}"}))
        return 1
    print(f"[{_now()}] MVP runtime starting on {project_path}")
    # 1. Scan (all applicable categories — Directive 1)
    print("  Step 1: scanning (code + security + dependencies)...")
    findings, scan_meta = _run_scanners(project_path)
    print(f"    -> {len(findings)} findings (deduped)")
    scope = _scope_completeness(scan_meta)
    # 2. Critic
    print("  Step 2: critic V2...")
    plan = _apply_critic(findings)
    if "error" in plan:
        print(f"    ERROR: {plan['error']}", file=sys.stderr)
        return 2
    plan["project"] = str(project_path)
    plan["mode"] = "complete"  # full scan of all applicable categories (Directive 1)
    plan["scope"] = {"scanners": scan_meta, **scope}
    plan.setdefault("critic_validation", {})["plan_completeness"] = scope["plan_completeness"]
    # 3. Plan
    _print_plan_summary(plan, project_path)
    _print_scope(scope)
    # 4. Confirm
    if not args.auto_confirm:
        confirmed = _confirm_human(plan)
        if not confirmed:
            print("  Aborted by human. Plan not applied.")
            if args.output:
                Path(args.output).write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
            return 3
    # 5. Dry-run
    print("  Step 5: dry-run patches:")
    cmds = _dry_run(plan)
    for cmd in cmds:
        print(f"    {cmd}")
    if args.dry_run_only:
        print("  (--dry-run-only: skipping KG persistence)")
    else:
        # Persist plan to KG via scan_periodic's _store_in_kg logic
        # (simplified: just write the plan JSON next to the project)
        out_path = Path(args.output) if args.output else Path(tempfile.gettempdir()) / "mvp_plan.json"
        out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Plan written to {out_path}")
    print(f"[{_now()}] MVP runtime done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
