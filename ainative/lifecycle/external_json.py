"""The owned entry inside a JSON configuration file.

`.claude/settings.json` belongs to the harness and the user. What the stack
needs from it is one hook entry: a PostToolUse group that runs the project's
summary regenerator after every Edit or Write. Replacing the file would destroy
whatever else it holds; leaving the entry to the user's memory is what made the
central automation a manual step.

So this module reads the document, takes back every entry it can prove it owns,
merges in exactly one canonical entry, and writes the document back with every
other key preserved. Ownership is the command target (`tools/ai_docs/run_hook`),
not a marker key: no harness schema has to tolerate a foreign field, and an
entry a user rewrote to run something else stops being ours — it is preserved,
never deleted. An unparsable document is refused, never rewritten.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INDENT = 2

_TARGET = re.compile(r'"([^"]*tools/ai_docs/run_hook\.[A-Za-z0-9]+)"')


@dataclass(frozen=True)
class HookSpec:
    event: str
    matcher: str
    command: str
    marker: str = "tools/ai_docs/run_hook"

    def canonical_entry(self) -> dict:
        return {"matcher": self.matcher,
                "hooks": [{"type": "command", "command": self.command}]}


def _load(path: Path) -> tuple[Any | None, str | None]:
    """(document, None), (None, reason) on error, or (None, None) when absent."""

    if not path.is_file():
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return None, f"unreadable: {error}"
    try:
        document = json.loads(text)
    except ValueError as error:
        return None, f"not valid JSON: {error}"
    if not isinstance(document, dict):
        return None, "the document is not a JSON object"
    return document, None


def _groups(document: dict, spec: HookSpec) -> list:
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return []
    groups = hooks.get(spec.event)
    return groups if isinstance(groups, list) else []


def owns_group(group: Any, spec: HookSpec) -> bool:
    if not isinstance(group, dict):
        return False
    entries = group.get("hooks")
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        command = entry.get("command")
        if isinstance(command, str) and spec.marker in command.replace("\\", "/"):
            return True
    return False


def _owned(document: dict, spec: HookSpec) -> list:
    return [group for group in _groups(document, spec) if owns_group(group, spec)]


def entry_command(path: Path, spec: HookSpec) -> str | None:
    """The command of the single owned entry, or None when it is not there."""

    document, error = _load(path)
    if error is not None or document is None:
        return None
    groups = _owned(document, spec)
    if len(groups) != 1:
        return None
    entries = groups[0].get("hooks")
    for entry in entries if isinstance(entries, list) else []:
        command = entry.get("command") if isinstance(entry, dict) else None
        if isinstance(command, str) and spec.marker in command.replace("\\", "/"):
            return command
    return None


def command_target(command: str) -> str | None:
    match = _TARGET.search(command.replace("\\", "/"))
    return match.group(1) if match else None


def apply(path: Path, spec: HookSpec) -> tuple[str | None, bool, str | None]:
    """(serialized document, changed, error). Creates the document when absent."""

    document, error = _load(path)
    if error is not None:
        return None, False, error
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    document = document if document is not None else {}
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        document["hooks"] = hooks
    groups = hooks.get(spec.event)
    kept = [group for group in groups if not owns_group(group, spec)] \
        if isinstance(groups, list) else []
    kept.append(spec.canonical_entry())
    hooks[spec.event] = kept
    rendered = json.dumps(document, indent=INDENT, sort_keys=True) + "\n"
    return rendered, rendered != before, None


def remove(path: Path, spec: HookSpec) -> tuple[str | None, bool, str | None]:
    """(serialized document or None to delete, changed, error)."""

    document, error = _load(path)
    if error is not None or document is None:
        return None, False, error
    before = path.read_text(encoding="utf-8")
    hooks = document.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            groups = hooks[event]
            if isinstance(groups, list):
                hooks[event] = [group for group in groups if not owns_group(group, spec)]
                if not hooks[event]:
                    del hooks[event]
        if not hooks:
            document.pop("hooks")
    if not document:
        return None, True, None
    rendered = json.dumps(document, indent=INDENT, sort_keys=True) + "\n"
    return rendered, rendered != before, None


def structural_status(path: Path, spec: HookSpec) -> tuple[str, str]:
    """Vocabulary: ABSENT_FILE | CONFIG_INVALID | NOT_CONFIGURED | DUPLICATE |
    COMMAND_INVALID | ENTRY_PRESENT."""

    document, error = _load(path)
    if error is not None:
        return "CONFIG_INVALID", error
    if document is None:
        return "ABSENT_FILE", "settings.json does not exist"
    groups = _owned(document, spec)
    if not groups:
        return "NOT_CONFIGURED", "no managed hook entry"
    if len(groups) > 1:
        return "DUPLICATE", f"{len(groups)} managed hook entries"
    command = entry_command(path, spec)
    if command is None:
        return "COMMAND_INVALID", "the managed entry has no readable command"
    if command_target(command) is None:
        return "COMMAND_INVALID", f"no wrapper path in {command!r}"
    return "ENTRY_PRESENT", command


__all__ = ["HookSpec", "apply", "remove", "structural_status", "entry_command",
           "command_target", "owns_group"]