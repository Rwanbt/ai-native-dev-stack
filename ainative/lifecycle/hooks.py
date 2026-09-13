"""What a project needs for its post-edit automation to actually run.

A settings.json entry proves nothing on its own: the command has to point at a
wrapper that exists, in this project, on this machine. This module owns the one
true spelling of that entry — the command string, the wrapper it names, and the
diagnosis — so the planner, `doctor` and the tests cannot drift apart.

The command is built with forward slashes on every platform: both bash and
PowerShell accept them, and it keeps one ownership marker
(`tools/ai_docs/run_hook`) valid on Windows and POSIX alike.
"""

from __future__ import annotations

import os
from pathlib import Path

from .external_json import (HookSpec, apply, command_target, entry_command,
                            remove, structural_status)

EVENT = "PostToolUse"
MATCHER = "Edit|Write"
WRAPPER_BASH = "tools/ai_docs/run_hook.sh"
WRAPPER_POWERSHELL = "tools/ai_docs/run_hook.ps1"
SETTINGS_RELATIVE = Path(".claude") / "settings.json"

# Doctor vocabulary.
CONFIGURED = "HOOK_CONFIGURED"
NOT_CONFIGURED = "HOOK_NOT_CONFIGURED"
TARGET_MISSING = "HOOK_TARGET_MISSING"
COMMAND_INVALID = "HOOK_COMMAND_INVALID"
CONFIG_INVALID = "HOOK_CONFIG_INVALID"
VERSION_MISMATCH = "HOOK_VERSION_MISMATCH"


def wrapper_relative(platform_name: str | None = None) -> str:
    return WRAPPER_POWERSHELL if (platform_name or os.name) == "nt" else WRAPPER_BASH


def hook_command(project: Path, platform_name: str | None = None) -> str:
    target = (Path(project).resolve() / wrapper_relative(platform_name)).as_posix()
    if (platform_name or os.name) == "nt":
        return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{target}"'
    return f'bash "{target}"'


def spec(project: Path, platform_name: str | None = None) -> HookSpec:
    return HookSpec(event=EVENT, matcher=MATCHER,
                    command=hook_command(project, platform_name))


def settings_path(project: Path) -> Path:
    return Path(project) / SETTINGS_RELATIVE


def apply_hook(project: Path, platform_name: str | None = None):
    selected = spec(project, platform_name)
    return apply(settings_path(project), selected)


def remove_hook(project: Path, platform_name: str | None = None):
    selected = spec(project, platform_name)
    return remove(settings_path(project), selected)


def hook_status(project: Path, platform_name: str | None = None) -> dict:
    """One diagnosis dict: status (doctor vocabulary), detail, path, command."""

    project = Path(project).resolve()
    selected = spec(project, platform_name)
    path = settings_path(project)
    structural, detail = structural_status(path, selected)

    if structural in ("CONFIG_INVALID", "DUPLICATE", "COMMAND_INVALID"):
        status = CONFIG_INVALID if structural != "COMMAND_INVALID" else COMMAND_INVALID
        return {"status": status, "detail": detail, "path": str(path),
                "command": None, "expected": selected.command}
    if structural in ("ABSENT_FILE", "NOT_CONFIGURED"):
        return {"status": NOT_CONFIGURED, "detail": detail, "path": str(path),
                "command": None, "expected": selected.command}

    command = entry_command(path, selected) or ""
    target = command_target(command)
    if target is None:
        return {"status": COMMAND_INVALID, "detail": f"no wrapper path in {command!r}",
                "path": str(path), "command": command, "expected": selected.command}
    if not Path(target).is_file():
        return {"status": TARGET_MISSING,
                "detail": f"the hook wrapper {target} does not exist",
                "path": str(path), "command": command, "expected": selected.command}
    if command != selected.command:
        return {"status": VERSION_MISMATCH,
                "detail": "the entry points at a different wrapper than this install "
                          "would configure",
                "path": str(path), "command": command, "expected": selected.command}
    return {"status": CONFIGURED, "detail": "", "path": str(path),
            "command": command, "expected": selected.command}


__all__ = ["EVENT", "MATCHER", "SETTINGS_RELATIVE", "spec", "settings_path",
           "apply_hook", "remove_hook", "hook_status", "wrapper_relative",
           "hook_command", "CONFIGURED", "NOT_CONFIGURED", "TARGET_MISSING",
           "COMMAND_INVALID", "CONFIG_INVALID", "VERSION_MISMATCH"]