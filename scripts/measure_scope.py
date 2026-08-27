#!/usr/bin/env python3
"""measure_scope.py — Keep AGENTS.md's scope figures honest.

AGENTS.md tells every agent how big this repo is and therefore how to read it.
That block went stale for ten weeks: it claimed 11 files and ~22 000 tokens
while the repo held 189 files and ~231 000, so the instruction "direct read
always" would have blown the context of any agent that obeyed it.

A measurement inside an instruction file is a fact with an expiry date. This
script re-measures and fails when AGENTS.md has drifted beyond tolerance.

Usage:
    python3 scripts/measure_scope.py            # verify (exit 1 on drift)
    python3 scripts/measure_scope.py --print    # just show current figures
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

STACK_ROOT = Path(__file__).resolve().parent.parent
ANTI_DEBT_PREFIX = "stack/agents/anti-debt/"

# Token estimate divisor used throughout AGENTS.md (bytes / 4).
BYTES_PER_TOKEN = 4

# Figures are rounded in the doc; fail only on a drift that changes the advice.
FILE_TOLERANCE = 0.15    # 15%
TOKEN_TOLERANCE = 0.20   # 20%


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(STACK_ROOT), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\n") if f and not f.endswith(".png")]


def measure(paths: list[str]) -> tuple[int, int]:
    """Return (file count, estimated tokens)."""
    total = 0
    count = 0
    for name in paths:
        path = STACK_ROOT / name
        try:
            total += path.stat().st_size
            count += 1
        except OSError:
            continue
    return count, total // BYTES_PER_TOKEN


def current_scopes() -> dict[str, tuple[int, int]]:
    files = tracked_files()
    core = [f for f in files if not f.startswith(ANTI_DEBT_PREFIX)]
    debt = [f for f in files if f.startswith(ANTI_DEBT_PREFIX)]
    return {
        "Core stack (excl. anti-debt)": measure(core),
        "Anti-debt agent": measure(debt),
        "Whole repo": measure(files),
    }


def declared_scopes(agents_md: str) -> dict[str, tuple[int, int]]:
    """Parse the scope table rows out of AGENTS.md."""
    declared: dict[str, tuple[int, int]] = {}
    row = re.compile(r"^\|\s*([^|]+?)\s*\|\s*~?([\d\s  ]+)\s*\|\s*(\d+)\s*\|", re.MULTILINE)
    for match in row.finditer(agents_md):
        label = match.group(1).strip()
        if label.startswith("Scope") or set(label) <= set("-: "):
            continue
        tokens = int(re.sub(r"[^\d]", "", match.group(2)))
        declared[label] = (int(match.group(3)), tokens)
    return declared


def drifted(actual: int, stated: int, tolerance: float) -> bool:
    if stated == 0:
        return actual != 0
    return abs(actual - stated) / stated > tolerance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--print", dest="show", action="store_true",
                        help="print current figures and exit 0")
    args = parser.parse_args()

    scopes = current_scopes()

    if args.show:
        for label, (files, tokens) in scopes.items():
            print(f"  {label:32} {files:4} files  ~{tokens:7} tokens")
        return 0

    agents_path = STACK_ROOT / "AGENTS.md"
    declared = declared_scopes(agents_path.read_text(encoding="utf-8"))

    errors: list[str] = []
    for label, (files, tokens) in scopes.items():
        if label not in declared:
            errors.append(f"AGENTS.md has no scope row for '{label}'")
            continue
        stated_files, stated_tokens = declared[label]
        if drifted(files, stated_files, FILE_TOLERANCE):
            errors.append(f"'{label}': {files} files, AGENTS.md says {stated_files}")
        if drifted(tokens, stated_tokens, TOKEN_TOLERANCE):
            errors.append(f"'{label}': ~{tokens} tokens, AGENTS.md says ~{stated_tokens}")
        if not errors or label not in " ".join(errors):
            print(f"OK: {label:32} {files:4} files  ~{tokens:7} tokens")

    if errors:
        print("\nAGENTS.md SCOPE DRIFT\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nUpdate the scope table in AGENTS.md — an agent reads it at "
              "session start\nto decide how to approach the codebase.", file=sys.stderr)
        return 1

    print("\nAGENTS.md scope figures match the repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
