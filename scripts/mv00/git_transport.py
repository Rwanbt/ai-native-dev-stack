"""Record inherited Git transport surfaces; sensitive transfer is fail-closed."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path


INHERITED = ("GIT_CONFIG_COUNT", "GIT_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND", "HTTP_PROXY", "HTTPS_PROXY", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")


@dataclass(frozen=True)
class GitTransportReport:
    schema_version: int
    recorded_at: str
    inherited_variables: tuple[str, ...]
    transport_qualified: bool
    sensitive_transfer_available: bool
    reason: str


def inspect(environment: dict[str, str] | None = None) -> GitTransportReport:
    environment = os.environ if environment is None else environment
    present = tuple(name for name in INHERITED if environment.get(name))
    reason = "parent transport environment must not be reused" if present else "effective Git configuration and actual transfer environment are unverified"
    return GitTransportReport(1, datetime.now(timezone.utc).isoformat(timespec="seconds"), present, False, False, reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(asdict(inspect()), sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
