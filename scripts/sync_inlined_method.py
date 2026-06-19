#!/usr/bin/env python3
"""sync_inlined_method.py — Refresh a STACK-managed block from AGENTS.md.

Some agents (e.g. MiniMax/Mavis) have no `@file` import — their config must
physically contain the method. To keep that copy from diverging, wrap the
region in markers and regenerate it from the canonical AGENTS.md:

    <!-- STACK:BEGIN vX.Y.Z — managed by ai-native-dev-stack, do not edit inside -->
    ... (replaced wholesale on every sync) ...
    <!-- STACK:END -->

Only the bytes between the markers are replaced; everything outside survives, so
the target's personal/tool-specific sections are never touched. This is the
non-destructive update path for inlined content (see UPDATING.md).

Usage:
    python3 scripts/sync_inlined_method.py <target-file> [--source AGENTS.md] [--check]

    --check : exit 1 if the block is stale (CI guard / pre-commit), write nothing.

If the target has no markers yet, the script prints where to add them and exits
non-zero — it never guesses an insertion point in a file it doesn't own.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BEGIN_RE = re.compile(r"^<!--\s*STACK:BEGIN.*?-->\s*$", re.MULTILINE)
END_RE = re.compile(r"^<!--\s*STACK:END\s*-->\s*$", re.MULTILINE)

STACK_ROOT = Path(__file__).resolve().parent.parent


def _stack_version(source: Path) -> str:
    m = re.search(r"stack-version:\s*([0-9][0-9A-Za-z.\-]*)", source.read_text(encoding="utf-8"))
    if m:
        return m.group(1)
    vf = STACK_ROOT / "VERSION"
    return vf.read_text(encoding="utf-8").strip() if vf.exists() else "0.0.0"


def _build_block(source: Path) -> str:
    version = _stack_version(source)
    body = source.read_text(encoding="utf-8").rstrip("\n")
    begin = (f"<!-- STACK:BEGIN v{version} — managed by ai-native-dev-stack from "
             f"AGENTS.md, do not edit inside (run scripts/sync_inlined_method.py) -->")
    end = "<!-- STACK:END -->"
    return f"{begin}\n\n{body}\n\n{end}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="File containing the STACK-managed block")
    ap.add_argument("--source", default=str(STACK_ROOT / "AGENTS.md"),
                    help="Canonical method file (default: AGENTS.md)")
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 if the block is stale; write nothing")
    args = ap.parse_args()

    target = Path(args.target)
    source = Path(args.source)
    if not target.exists():
        print(f"ERROR: target not found: {target}")
        return 2
    if not source.exists():
        print(f"ERROR: source not found: {source}")
        return 2

    content = target.read_text(encoding="utf-8")
    bm, em = BEGIN_RE.search(content), END_RE.search(content)
    if not bm or not em or bm.start() >= em.start():
        print("ERROR: no STACK:BEGIN/STACK:END block found in the target.")
        print("Add these two markers around the region you want managed, then re-run:")
        print("  <!-- STACK:BEGIN — managed by ai-native-dev-stack -->")
        print("  <!-- STACK:END -->")
        return 3

    new_block = _build_block(source)
    new_content = content[:bm.start()] + new_block + content[em.end():]

    if new_content == content:
        print(f"OK: {target.name} already in sync.")
        return 0

    if args.check:
        print(f"STALE: {target.name} differs from {source.name} — run without --check to sync.")
        return 1

    backup = target.with_suffix(target.suffix + ".bak")
    backup.write_text(content, encoding="utf-8")
    target.write_text(new_content, encoding="utf-8")
    print(f"SYNCED: {target.name} updated from {source.name} (backup: {backup.name}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
