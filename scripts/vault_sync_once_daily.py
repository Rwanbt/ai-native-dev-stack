#!/usr/bin/env python3
"""vault_sync_once_daily.py — Run the vault sync at most once per day.

The sentinel is written ONLY when the sync actually succeeded. The previous
version wrote it unconditionally, so a day that ended in a divergence — with
nothing pushed — was recorded as "synced today" and no further attempt was
made until the next morning. A failed backup marked the day done.

Usage:
    python3 scripts/vault_sync_once_daily.py [--vault PATH] [--force]

Vault location, in order: --vault, $OBSIDIAN_VAULT, error.
Sentinel: $OBSIDIAN_SYNC_STATE, else alongside this script.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = SCRIPT_DIR / "vault_sync.py"


def sentinel_path() -> Path:
    override = os.environ.get("OBSIDIAN_SYNC_STATE")
    return Path(override) if override else SCRIPT_DIR / "vault_last_sync_date.txt"


def already_synced_today(sentinel: Path, today: str) -> bool:
    try:
        return sentinel.read_text(encoding="utf-8").strip() == today
    except OSError:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument("--force", action="store_true",
                        help="sync even if already done today")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = time.strftime("%Y-%m-%d")
    sentinel = sentinel_path()

    if not args.force and already_synced_today(sentinel, today):
        print(f"vault: already synced today ({today}) — skip")
        return 0

    if not SYNC_SCRIPT.is_file():
        print(f"vault: {SYNC_SCRIPT} not found — skip", file=sys.stderr)
        return 1

    command = [sys.executable, str(SYNC_SCRIPT)]
    if args.vault:
        command += ["--vault", str(args.vault)]

    result = subprocess.run(command, env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    if result.returncode != 0:
        # Do NOT record the day: the point of the sentinel is to skip work
        # already done, not to suppress retries after a failure.
        print(f"vault: sync failed (exit {result.returncode}) — "
              f"day NOT marked, will retry next session", file=sys.stderr)
        return result.returncode

    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(today, encoding="utf-8")
    except OSError as err:
        print(f"vault: synced, but could not write the sentinel ({err})", file=sys.stderr)
        return 0

    print(f"vault: first session of {today} — sync done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
