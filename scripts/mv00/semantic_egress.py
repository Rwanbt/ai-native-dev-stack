"""Inspect Smart Connections metadata without exposing vault settings or notes."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path


class SemanticEgress(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SemanticEgressReport:
    schema_version: int
    recorded_at: str
    plugin_present: bool
    plugin_enabled: bool | None
    plugin_version: str | None
    setting_keys: tuple[str, ...]
    observation_mechanism: str
    semantic_background_egress: SemanticEgress
    sensitive_semantic_available: bool
    reason: str


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def inspect(vault_root: Path) -> SemanticEgressReport:
    """Collect only plugin metadata and setting names; values never leave the process."""

    plugin = vault_root / ".obsidian" / "plugins" / "smart-connections"
    manifest = _read_json(plugin / "manifest.json")
    settings = _read_json(plugin / "data.json")
    enabled = _read_json(vault_root / ".obsidian" / "community-plugins.json")
    present = isinstance(manifest, dict)
    enabled_value = "smart-connections" in enabled if isinstance(enabled, list) else None
    version = str(manifest.get("version")) if present and manifest.get("version") else None
    keys = tuple(sorted(str(key) for key in settings)) if isinstance(settings, dict) else ()
    return _report(present, enabled_value, version, keys)


def _report(present: bool, enabled: bool | None, version: str | None, keys: tuple[str, ...]) -> SemanticEgressReport:
    if not present:
        result, reason = SemanticEgress.NONE, "Smart Connections manifest is absent"
    elif not enabled:
        result, reason = SemanticEgress.NONE, "plugin is not enabled"
    else:
        result, reason = SemanticEgress.UNKNOWN, "no qualified runtime network observation mechanism exists"
    return SemanticEgressReport(1, datetime.now(timezone.utc).isoformat(timespec="seconds"), present, enabled, version, keys, "none", result, False, reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect(args.vault_root)
    encoded = json.dumps(asdict(report), sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
