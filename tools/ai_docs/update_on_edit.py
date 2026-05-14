#!/usr/bin/env python3
"""
update_on_edit.py — Claude Code PostToolUse hook.

Triggered after every Edit/Write tool call. Reads the tool input JSON
from stdin, determines which Seno module was affected, and regenerates
that module's AI_SUMMARY.md.

Registered in .claude/settings.json:
    PostToolUse → Edit|Write → this script

Never blocks Claude Code: always exits 0 (errors go to stderr only).
"""

import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent.resolve()
SENO_ROOT = _SCRIPT_DIR.parent.parent  # tools/ai_docs/../../

# Ordered from most-specific to least-specific so the first match wins.
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

WATCHED_EXTENSIONS = {".cpp", ".h", ".hpp", ".rs"}


def find_module(file_path: str) -> Path | None:
    try:
        resolved = Path(file_path).resolve()
    except Exception:
        return None

    for rel in MODULE_DIRS:
        candidate = (SENO_ROOT / rel).resolve()
        try:
            resolved.relative_to(candidate)
            return candidate
        except ValueError:
            continue
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return 0  # not a JSON hook event — skip silently

    # Claude Code PostToolUse passes: { tool_name, tool_input, tool_response }
    tool_input = data.get("tool_input", data)
    file_path: str = tool_input.get("file_path", "")

    if not file_path:
        return 0

    suffix = Path(file_path).suffix.lower()
    if suffix not in WATCHED_EXTENSIONS:
        return 0

    module_dir = find_module(file_path)
    if module_dir is None:
        return 0  # file not in a tracked module

    generator = _SCRIPT_DIR / "generate_ai_summary.py"
    if not generator.exists():
        print(f"[ai_docs] generator not found: {generator}", file=sys.stderr)
        return 0

    result = subprocess.run(
        [sys.executable, str(generator), str(module_dir)],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode == 0:
        # Print to stderr so it appears as a hook notification in the UI
        msg = result.stdout.strip()
        if msg:
            print(f"[ai_docs] {msg}", file=sys.stderr)
    else:
        print(f"[ai_docs] warning: {result.stderr.strip()}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ai_docs] unhandled error: {exc}", file=sys.stderr)
        sys.exit(0)  # never block Claude Code
