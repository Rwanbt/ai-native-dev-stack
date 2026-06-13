#!/usr/bin/env python3
"""
update_on_edit.py — Claude Code PostToolUse hook.

Triggered after every Edit/Write tool call. Reads the tool input JSON
from stdin, finds which module was affected by walking up the directory
tree until an AI_CONTEXT.md is found, then regenerates that module's
AI_SUMMARY.md.

Works for any project structure — no hardcoded paths.

Registered in .claude/settings.json:
    PostToolUse → Edit|Write → this script

Never blocks Claude Code: always exits 0 (errors go to stderr only).
"""

from __future__ import annotations  # PEP 563 — keep `X | None` valid on Python 3.8/3.9

import json
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent.resolve()
GENERATOR = _SCRIPT_DIR / "generate_ai_summary.py"

# File extensions that trigger an AI_SUMMARY.md update — single source of truth
from source_config import ALL_SOURCE_EXTS as WATCHED_EXTENSIONS  # noqa: E402
from module_discovery import find_module  # noqa: E402


CONTEXT_STALE_DAYS = 30  # warn if AI_CONTEXT.md not touched in this many days while sources changed


def check_context_freshness(module_dir: Path) -> None:
    """
    Warn when AI_CONTEXT.md is older than CONTEXT_STALE_DAYS and at least one
    source file in the module has been modified since. Emits a single line to
    stderr — never raises, never blocks Claude Code.
    """
    context_file = module_dir / "AI_CONTEXT.md"
    if not context_file.exists():
        return

    try:
        context_mtime = context_file.stat().st_mtime
        age_days = (time.time() - context_mtime) / 86400

        if age_days < CONTEXT_STALE_DAYS:
            return  # recently updated — no drift

        # Any source file newer than AI_CONTEXT.md?
        for src in module_dir.iterdir():
            if src.suffix.lower() in WATCHED_EXTENSIONS:
                if src.stat().st_mtime > context_mtime:
                    print(
                        f"[ai_docs] ⚠️  DRIFT {module_dir.name}/AI_CONTEXT.md "
                        f"({int(age_days)}d old, sources updated since) — "
                        f"review AI_CONTEXT.md before next commit.",
                        file=sys.stderr,
                    )
                    return  # one warning per hook call is enough
    except Exception:
        pass  # never block Claude Code



def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return 0  # not a JSON hook event — skip silently

    # Claude Code PostToolUse payload: { tool_name, tool_input, tool_response }
    tool_input = data.get("tool_input", data)
    file_path: str = tool_input.get("file_path", "")

    if not file_path:
        return 0

    if Path(file_path).suffix.lower() not in WATCHED_EXTENSIONS:
        return 0  # not a source file — skip

    module_dir = find_module(file_path)
    if module_dir is None:
        return 0  # no AI_CONTEXT.md in the ancestor chain

    if not GENERATOR.exists():
        print(f"[ai_docs] generator not found: {GENERATOR}", file=sys.stderr)
        return 0

    result = subprocess.run(
        [sys.executable, str(GENERATOR), str(module_dir)],
        capture_output=True,
        text=True,
        timeout=15,
    )

    if result.returncode == 0:
        msg = result.stdout.strip()
        if msg:
            print(f"[ai_docs] {msg}", file=sys.stderr)
    else:
        print(f"[ai_docs] warning: {result.stderr.strip()}", file=sys.stderr)

    # Drift detection — runs after every successful AI_SUMMARY update
    check_context_freshness(module_dir)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ai_docs] unhandled error: {exc}", file=sys.stderr)
        sys.exit(0)  # never block Claude Code
