"""Inventory project-local harness autoload surfaces without executing them."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


AUTLOAD_NAMES = frozenset({"AGENTS.md", "CLAUDE.md", "settings.json", "settings.local.json", "mcp.json", "opencode.json"})


@dataclass(frozen=True)
class HarnessAutoloadReport:
    schema_version: int
    recorded_at: str
    checkout: str
    surfaces: tuple[str, ...]
    disable_control: str
    observation: str
    sensitive_harness_available: bool
    reason: str


def inventory(checkout: Path) -> HarnessAutoloadReport:
    """Names are evidence of a potential autoload surface, not executable trust."""

    surfaces = tuple(sorted(path.relative_to(checkout).as_posix() for path in checkout.rglob("*") if path.is_file() and path.name in AUTLOAD_NAMES))
    reason = "project autoload surfaces require a harness-specific neutral-launch probe" if surfaces else "no recognized project-local autoload surface was found"
    return HarnessAutoloadReport(1, datetime.now(timezone.utc).isoformat(timespec="seconds"), str(checkout), surfaces, "UNKNOWN", "none", False, reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(asdict(inventory(args.checkout)), sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
