#!/usr/bin/env python3
"""
generate_all.py — Regenerate AI_SUMMARY.md for every module in the project.

A module is any directory that contains an AI_CONTEXT.md file.
No hardcoded paths — works for any project structure and any language.

Usage:
    python tools/ai_docs/generate_all.py [--dry-run] [--root /path/to/project]

The script auto-discovers modules by scanning for AI_CONTEXT.md files,
skipping .git, node_modules, vendor, __pycache__, and build directories.
"""

import subprocess
import sys
from pathlib import Path

# Directories to never scan (common build / cache / vendor dirs)
SKIP_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__", ".cache",
    "build", "dist", "target", ".venv", "venv", "env",
    ".tox", "coverage", ".nyc_output", "out", "bin", "obj",
    ".gradle", ".idea", ".vscode",
}

GENERATOR = Path(__file__).parent / "generate_ai_summary.py"


def find_project_root(start: Path) -> Path:
    """Walk up from start to find the git root, or use start as fallback."""
    p = start
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return start


def discover_modules(root: Path) -> list[Path]:
    """Find all directories containing AI_CONTEXT.md, skipping noise dirs."""
    modules = []
    for ctx in sorted(root.rglob("AI_CONTEXT.md")):
        # Skip if any parent component is in SKIP_DIRS
        parts = set(ctx.parts)
        if parts & SKIP_DIRS:
            continue
        modules.append(ctx.parent)
    return modules


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    # Allow explicit root override: python generate_all.py --root /path
    root = None
    if "--root" in sys.argv:
        idx = sys.argv.index("--root")
        if idx + 1 < len(sys.argv):
            root = Path(sys.argv[idx + 1]).resolve()
    if root is None:
        root = find_project_root(Path(__file__).parent)

    modules = discover_modules(root)

    if not modules:
        print(f"No AI_CONTEXT.md files found under {root}")
        print("Create an AI_CONTEXT.md in each module directory first.")
        print("See templates/AI_CONTEXT_template.md for the format.")
        return 1

    print(f"Found {len(modules)} module(s) under {root}")
    ok = failed = 0

    for module_dir in modules:
        rel = module_dir.relative_to(root)
        if dry_run:
            print(f"  would update  {rel}/AI_SUMMARY.md")
            ok += 1
            continue

        result = subprocess.run(
            [sys.executable, str(GENERATOR), str(module_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            short = result.stdout.strip().replace(str(root), "")
            print(f"  OK  {short or rel}")
            ok += 1
        else:
            print(f"  ERR {rel}: {result.stderr.strip()}")
            failed += 1

    print(f"\nDone: {ok} updated, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
