#!/usr/bin/env python3
"""
generate_all.py — Regenerate AI_SUMMARY.md for every Seno DAW module.

Run this after adding new files or when AI_SUMMARY.md files are stale.

Usage:
    python tools/ai_docs/generate_all.py [--dry-run]
"""

import subprocess
import sys
from pathlib import Path

SENO_ROOT = Path(__file__).parent.parent.parent

MODULE_DIRS = [
    "app/Source/Core/Audio",
    "app/Source/Core/IO",
    "app/Source/Core/Edit",
    "app/Source/Core/Export",
    "app/Source/Core/Streaming",
    "app/Source/Core/Midi",
    "app/Source/Core/Recording",
    "app/Source/Core/Script",
    "app/Source/Core/Input",
    "app/Source/Core/Undo",
    "app/Source/Core/Diagnostics",
    "app/Source/UI",
    "rust_dsp/src",
]

generator = Path(__file__).parent / "generate_ai_summary.py"


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    ok = 0
    skipped = 0
    failed = 0

    for rel in MODULE_DIRS:
        module_abs = SENO_ROOT / rel
        if not module_abs.exists():
            print(f"  skip  {rel}  (directory not found)")
            skipped += 1
            continue

        if dry_run:
            print(f"  would update  {rel}/AI_SUMMARY.md")
            ok += 1
            continue

        result = subprocess.run(
            [sys.executable, str(generator), str(module_abs)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            short = result.stdout.strip().replace(str(SENO_ROOT), "")
            print(f"  OK  {short}")
            ok += 1
        else:
            print(f"  ERR {rel}: {result.stderr.strip()}")
            failed += 1

    print(f"\nDone: {ok} updated, {skipped} skipped, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
