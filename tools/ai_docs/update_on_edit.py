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

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent.resolve()
GENERATOR = _SCRIPT_DIR / "generate_ai_summary.py"

# File extensions that trigger an AI_SUMMARY.md update
WATCHED_EXTENSIONS = {
    # C / C++
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    # Rust
    ".rs",
    # TypeScript / JavaScript
    ".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs",
    # Python
    ".py",
    # Go
    ".go",
    # Java / Kotlin
    ".java", ".kt",
    # C# / F#
    ".cs", ".fs",
    # Swift
    ".swift",
    # Ruby
    ".rb",
    # PHP
    ".php",
}

# Directories to skip when walking up (avoid matching project-root accidentaly)
STOP_DIRS = {".git", "node_modules", "vendor", "__pycache__"}


def find_module(file_path: str) -> Path | None:
    """
    Walk up the directory tree from file_path.
    Return the first directory that contains AI_CONTEXT.md.
    Stop at the git root (directory containing .git) or filesystem root.
    """
    try:
        current = Path(file_path).resolve().parent
    except Exception:
        return None

    visited = set()
    while current not in visited:
        visited.add(current)

        # Found a module marker
        if (current / "AI_CONTEXT.md").exists():
            return current

        # Stop at git root or filesystem root
        if (current / ".git").exists() or current == current.parent:
            return None

        # Don't ascend through noisy dirs
        if current.name in STOP_DIRS:
            return None

        current = current.parent

    return None


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

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ai_docs] unhandled error: {exc}", file=sys.stderr)
        sys.exit(0)  # never block Claude Code
