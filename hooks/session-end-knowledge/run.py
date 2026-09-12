"""Thin SessionEnd adapter: shells out to the authoritative CLI. No policy here.

Contract: never block the session (exit 0 on every path), never mutate
canonical files, never promote, never write outside the project store. The
project root comes from the hook stdin JSON (`cwd`), then AINATIVE_PROJECT,
then the current directory, and every CLI call runs with that directory as
its working directory (the CLIs are project-relative by default).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CLI_CALLS = [
    ["context", "checkpoint", "--state-json", '{"task": "session end checkpoint"}'],
    ["knowledge", "consolidate"],
]


def _project() -> Path:
    payload = {}
    if not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            payload = {}
    candidate = (os.environ.get("AINATIVE_PROJECT")
                 or (payload.get("cwd") if isinstance(payload, dict) else None)
                 or os.getcwd())
    return Path(candidate)


def _cli() -> list[str]:
    override = os.environ.get("AINATIVE_BIN")
    if override:
        return [override]
    found = shutil.which("ainative")
    if found:
        return [found]
    return [sys.executable, "-m", "ainative"]


def main() -> int:
    project = _project()
    if not (project / ".ai-native").is_dir():
        print("ai-native: no project state; nothing to do")
        return 0
    for arguments in CLI_CALLS:
        command = _cli() + list(arguments)
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=60, check=False, cwd=str(project))
        except (OSError, subprocess.SubprocessError) as error:
            print(f"ai-native: hook step failed safely: {error}", file=sys.stderr)
            continue
        if completed.stdout.strip():
            print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
