#!/usr/bin/env python3
"""
generate_metrics.py — AI-Native Dev Stack metrics snapshot.

Generates docs/METRICS.md with objective, git-derived measurements:
  - AI_CONTEXT.md coverage (% of source directories covered)
  - AI_SUMMARY.md freshness
  - AI_CONTEXT.md drift (stale docs where sources changed)
  - KNOWN_FAILURE_PATTERNS count (proxy for bugs caught by the system)
  - ADR count
  - High-churn uncovered directories (risk zones)
  - Trend table (one row per run, append-only)

Usage:
    python tools/ai_docs/generate_metrics.py [--project-root /path] [--stdout]

Outputs docs/METRICS.md by default. Pass --stdout to print instead.
Always exits 0.
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import time

# ── Configuration ─────────────────────────────────────────────────────────────

SOURCE_EXTENSIONS = {
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    ".rs",
    ".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs",
    ".py",
    ".go",
    ".java", ".kt",
    ".cs", ".fs",
    ".swift",
    ".rb",
    ".php",
}

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__",
    "build", "dist", "target", ".cache", ".next",
    "AI_SUMMARY.md", "AI_CONTEXT.md",
}

CONTEXT_STALE_DAYS = 30
HIGH_CHURN_COMMITS = 5   # commits in last 30 days = "high churn"


# ── Helpers ───────────────────────────────────────────────────────────────────

def git_run(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def find_source_dirs(root: Path) -> list[Path]:
    """Return all directories that contain at least one source file."""
    dirs: set[Path] = set()
    for ext in SOURCE_EXTENSIONS:
        for f in root.rglob(f"*{ext}"):
            if not any(p in SKIP_DIRS for p in f.parts):
                dirs.add(f.parent)
    return sorted(dirs)


def find_context_modules(root: Path) -> list[Path]:
    """Return all directories that have AI_CONTEXT.md."""
    return sorted(
        p.parent
        for p in root.rglob("AI_CONTEXT.md")
        if not any(s in SKIP_DIRS for s in p.parts)
    )


def is_summary_stale(module_dir: Path) -> bool:
    summary = module_dir / "AI_SUMMARY.md"
    if not summary.exists():
        return True
    s_mtime = summary.stat().st_mtime
    for src in module_dir.iterdir():
        if src.suffix.lower() in SOURCE_EXTENSIONS:
            if src.stat().st_mtime > s_mtime:
                return True
    return False


def is_context_stale(module_dir: Path) -> tuple[bool, int]:
    """Return (is_stale, age_in_days)."""
    ctx = module_dir / "AI_CONTEXT.md"
    if not ctx.exists():
        return False, 0
    age_days = int((time.time() - ctx.stat().st_mtime) / 86400)
    if age_days < CONTEXT_STALE_DAYS:
        return False, age_days
    for src in module_dir.iterdir():
        if src.suffix.lower() in SOURCE_EXTENSIONS:
            if src.stat().st_mtime > ctx.stat().st_mtime:
                return True, age_days
    return False, age_days


def count_kfp_patterns(root: Path) -> int:
    """Count ### headings in KNOWN_FAILURE_PATTERNS.md (one per pattern)."""
    for candidate in [
        root / "docs" / "KNOWN_FAILURE_PATTERNS.md",
        root / "KNOWN_FAILURE_PATTERNS.md",
    ]:
        if candidate.exists():
            return sum(1 for line in candidate.read_text(encoding="utf-8").splitlines()
                       if line.startswith("### "))
    return 0


def count_adrs(root: Path) -> int:
    for d in [root / "docs" / "adr", root / "docs" / "decisions", root / "docs" / "adrs"]:
        if d.is_dir():
            return sum(1 for f in d.glob("*.md") if f.name.lower() != "readme.md")
    return 0


def high_churn_uncovered(root: Path, source_dirs: list[Path],
                          covered_dirs: list[Path]) -> list[tuple[Path, int]]:
    """Return uncovered dirs with >HIGH_CHURN_COMMITS commits in last 30 days."""
    covered_set = set(covered_dirs)
    results = []
    for d in source_dirs:
        if d in covered_set:
            continue
        rel = d.relative_to(root)
        log = git_run(
            ["log", "--oneline", "--since=30 days ago", "--", str(rel)],
            cwd=root,
        )
        count = len([l for l in log.splitlines() if l.strip()])
        if count >= HIGH_CHURN_COMMITS:
            results.append((d, count))
    return sorted(results, key=lambda x: -x[1])


# ── Trend table helpers ────────────────────────────────────────────────────────

TREND_HEADER = "| Date | Coverage | KFP patterns | ADRs | Stale contexts | Risk zones |"
TREND_SEP    = "|------|----------|--------------|------|----------------|------------|"


def load_existing_trend(metrics_path: Path) -> list[str]:
    """Extract existing trend rows from METRICS.md (skip header + sep)."""
    if not metrics_path.exists():
        return []
    lines = metrics_path.read_text(encoding="utf-8").splitlines()
    rows = []
    in_table = False
    for line in lines:
        if line.strip() == TREND_HEADER.strip():
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            rows.append(line)
        elif in_table:
            in_table = False
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def generate(root: Path, to_stdout: bool = False) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    project = root.name

    source_dirs   = find_source_dirs(root)
    covered_dirs  = find_context_modules(root)
    total_src     = len(source_dirs)
    total_covered = len(covered_dirs)
    pct           = int(100 * total_covered / total_src) if total_src else 0

    stale_summaries = [d for d in covered_dirs if is_summary_stale(d)]
    fresh_summaries = total_covered - len(stale_summaries)

    stale_contexts: list[tuple[Path, int]] = []
    for d in covered_dirs:
        is_s, age = is_context_stale(d)
        if is_s:
            stale_contexts.append((d, age))

    kfp_count   = count_kfp_patterns(root)
    adr_count   = count_adrs(root)
    risk_zones  = high_churn_uncovered(root, source_dirs, covered_dirs)

    # ── Cognitive contract coverage ───────────────────────────────────────────
    full_contract = 0
    for d in covered_dirs:
        ctx = (d / "AI_CONTEXT.md").read_text(encoding="utf-8", errors="replace")
        if "## Common failure modes" in ctx and "## Hot files" in ctx:
            full_contract += 1

    # ── Build report ──────────────────────────────────────────────────────────
    lines: list[str] = []
    lines += [
        f"# AI Stack Metrics — {project} — {today}",
        "",
        "> Auto-generated by `tools/ai_docs/generate_metrics.py`. Do not edit manually.",
        "",
    ]

    # Coverage
    lines += [
        "## Coverage",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Source directories | {total_src} |",
        f"| Directories with `AI_CONTEXT.md` | {total_covered} ({pct}%) |",
        f"| Full cognitive contract (failure modes + hot files) | {full_contract} / {total_covered} |",
        "",
    ]

    if covered_dirs:
        lines += ["### Covered modules", ""]
        for d in covered_dirs:
            rel = d.relative_to(root)
            stale_s = "⚠️ summary stale" if is_summary_stale(d) else "✅"
            is_ctx_s, age = is_context_stale(d)
            ctx_tag = f"⚠️ context {age}d old" if is_ctx_s else ""
            tag = " · ".join(t for t in [stale_s, ctx_tag] if t)
            lines.append(f"- `{rel}` — {tag}")
        lines.append("")

    # Freshness
    lines += [
        "## Freshness",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| `AI_SUMMARY.md` up to date | {fresh_summaries} / {total_covered} |",
        f"| `AI_CONTEXT.md` potentially stale (>{CONTEXT_STALE_DAYS}d, sources modified) "
        f"| {len(stale_contexts)} module(s) |",
        "",
    ]

    if stale_contexts:
        lines += ["### Stale contexts — review before next commit", ""]
        for d, age in sorted(stale_contexts, key=lambda x: -x[1]):
            rel = d.relative_to(root)
            lines.append(f"- `{rel}` — `AI_CONTEXT.md` is {age} days old, sources updated since")
        lines.append("")

    # Knowledge base
    lines += [
        "## Knowledge Base",
        "",
        f"| Artifact | Count | Signal |",
        f"|----------|-------|--------|",
        f"| `KNOWN_FAILURE_PATTERNS.md` patterns | {kfp_count} | "
        + ("Bugs caught by the system — grow this over time" if kfp_count > 0 else "⚠️ Not started — create `docs/KNOWN_FAILURE_PATTERNS.md`")
        + " |",
        f"| ADRs (`docs/adr/`) | {adr_count} | "
        + ("Architectural decisions documented" if adr_count > 0 else "⚠️ None — document at least ADR-0001")
        + " |",
        "",
    ]

    # Risk zones
    lines += [
        "## Risk Zones (high churn, no AI_CONTEXT.md)",
        "",
    ]
    if risk_zones:
        lines += [
            f"Directories with ≥{HIGH_CHURN_COMMITS} commits in the last 30 days and no `AI_CONTEXT.md`:",
            "",
        ]
        for d, commits in risk_zones:
            rel = d.relative_to(root)
            lines.append(f"- `{rel}` — {commits} commits (30d) — **add AI_CONTEXT.md**")
    else:
        lines.append("No high-churn uncovered directories detected. ✅")
    lines.append("")

    # Trend table (append-only)
    metrics_path = root / "docs" / "METRICS.md"
    existing_rows = load_existing_trend(metrics_path)
    new_row = (
        f"| {today} | {pct}% ({total_covered}/{total_src}) | {kfp_count} | {adr_count} "
        f"| {len(stale_contexts)} | {len(risk_zones)} |"
    )
    # Deduplicate: don't add two rows for the same date
    today_prefix = f"| {today} "
    rows = [r for r in existing_rows if not r.startswith(today_prefix)]
    rows.append(new_row)

    lines += [
        "## Trend",
        "",
        TREND_HEADER,
        TREND_SEP,
    ]
    lines += rows
    lines += ["", f"_Last updated: {today}_", ""]

    output = "\n".join(lines)

    if to_stdout:
        print(output)
        return

    out_path = root / "docs" / "METRICS.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(f"[metrics] Written to {out_path} ({len(lines)} lines)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI stack metrics snapshot")
    parser.add_argument("--project-root", default=".", help="Project root (default: cwd)")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of file")
    args = parser.parse_args()

    try:
        root = Path(args.project_root).resolve()
        generate(root, to_stdout=args.stdout)
    except Exception as exc:
        print(f"[metrics] error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
