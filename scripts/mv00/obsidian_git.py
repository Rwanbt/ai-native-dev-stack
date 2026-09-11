"""Detect potential Obsidian Git writers without emitting settings or remotes."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path


class WriterState(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ObsidianGitReport:
    schema_version: int
    recorded_at: str
    plugin_present: bool
    plugin_enabled: bool | None
    plugin_version: str | None
    setting_keys: tuple[str, ...]
    concurrent_writer: WriterState
    sensitive_sync_available: bool
    reason: str


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def inspect(vault_root: Path) -> ObsidianGitReport:
    """A plugin can be enabled without proving its current scheduling or network state."""

    plugin = vault_root / ".obsidian" / "plugins" / "obsidian-git"
    manifest = _read_json(plugin / "manifest.json")
    settings = _read_json(plugin / "data.json")
    enabled = _read_json(vault_root / ".obsidian" / "community-plugins.json")
    present = isinstance(manifest, dict)
    enabled_value = "obsidian-git" in enabled if isinstance(enabled, list) else None
    version = str(manifest.get("version")) if present and manifest.get("version") else None
    keys = tuple(sorted(str(key) for key in settings)) if isinstance(settings, dict) else ()
    state, reason = _classify(present, enabled_value)
    return ObsidianGitReport(1, datetime.now(timezone.utc).isoformat(timespec="seconds"), present, enabled_value, version, keys, state, False, reason)


def _classify(present: bool, enabled: bool | None) -> tuple[WriterState, str]:
    if not present:
        return WriterState.INACTIVE, "Obsidian Git manifest is absent"
    if enabled is False:
        return WriterState.INACTIVE, "Obsidian Git is disabled"
    return WriterState.UNKNOWN, "plugin is installed but current sync scheduling and process activity are unobserved"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(asdict(inspect(args.vault_root)), sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
