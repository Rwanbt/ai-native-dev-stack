"""Tests for scripts/vault_sync.py v4 integration.

Covers:
  * maintenance lock halts the sync before any fetch
  * v4 vault passes the validator and pushes a commit
  * v4 vault fails the validator and the index is reset to its prior state
  * --no-validator-check is the only opt-out
  * non-v4 vault: original behaviour preserved
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STACK = Path(__file__).resolve().parents[2]
SYNC = STACK / "scripts" / "vault_sync.py"


def _run(args: list[str], env: dict | None = None,
         cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SYNC), *args]
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(cmd, env=full_env, capture_output=True, text=True,
                          cwd=str(cwd) if cwd else None, timeout=60)


def _build_v4_vault(root: Path, *, validator: str) -> Path:
    """Lay down a v4 vault with the supplied validator body."""
    (root / "AGENTS.md").write_text("# vault\n", encoding="utf-8")
    system = root / "_system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "AGENTS.md").write_text("# system\n", encoding="utf-8")
    (system / "schemas").mkdir(parents=True, exist_ok=True)
    (system / "schemas" / "projects.json").write_text(json.dumps({
        "schema_version": 4,
        "projects": [
            {"slug": "demo", "title": "Demo", "prefix": "DEMO",
             "source": "Demo", "status": "active"},
        ],
    }), encoding="utf-8")
    (system / "tooling").mkdir(parents=True, exist_ok=True)
    (system / "tooling" / "vault.py").write_text(validator, encoding="utf-8")
    (system / "tooling" / "vaultlib.py").write_text("", encoding="utf-8")
    return root


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=check,
    )
    return result.stdout.strip()


def _init_vault_git(root: Path, remote: Path) -> None:
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.email", "ci@example.com")
    _git(root, "config", "user.name", "CI")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "-u", "origin", "master")
    _git(root, "remote", "set-head", "origin", "-a")


GREEN_VALIDATOR = (
    "import argparse, sys\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--root', default='.')\n"
    "sub = p.add_subparsers(dest='cmd', required=True)\n"
    "sub.add_parser('lint')\n"
    "sub.add_parser('check')\n"
    "args = p.parse_args()\n"
    "if args.cmd in ('lint', 'check'):\n"
    "    print('OK')\n"
    "    sys.exit(0)\n"
)

RED_VALIDATOR = (
    "import argparse, sys\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--root', default='.')\n"
    "sub = p.add_subparsers(dest='cmd', required=True)\n"
    "sub.add_parser('lint')\n"
    "sub.add_parser('check')\n"
    "args = p.parse_args()\n"
    "sys.stderr.write('lint failed')\n"
    "sys.exit(1)\n"
)


class SyncV4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="stack-sync-v4-")
        self.tmp = Path(self._tmp)
        self.remote = self.tmp / "remote.git"
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.remote.mkdir()
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- maintenance lock ----------------------------------------------

    def test_maintenance_lock_halts_before_fetch(self) -> None:
        _build_v4_vault(self.vault, validator=GREEN_VALIDATOR)
        _init_vault_git(self.vault, self.remote)
        (self.vault / ".git" / "maintenance.lock").write_text("gate-0", encoding="utf-8")
        (self.vault / "note.md").write_text("dirty", encoding="utf-8")
        result = _run(["--vault", str(self.vault), "--skip-secret-scan"])
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("maintenance", result.stderr.lower())
        # No path should be staged (the maintenance check fires before
        # `git add`). The untracked file in the working tree is
        # expected — the test only proves the sync did not commit it.
        porcelain = _git(self.vault, "status", "--porcelain")
        self.assertFalse(
            any(line.startswith("A ") or line.startswith("M ") for line in porcelain.splitlines()),
            "maintenance lock should leave the index clean",
        )
        # The remote was never touched: still only the "init" commit.
        log = _git(self.vault, "log", "--oneline")
        self.assertEqual(len(log.splitlines()), 1)

    # --- green validator path ------------------------------------------

    def test_green_validator_lets_sync_push(self) -> None:
        _build_v4_vault(self.vault, validator=GREEN_VALIDATOR)
        _init_vault_git(self.vault, self.remote)
        (self.vault / "note.md").write_text("hello", encoding="utf-8")
        result = _run(["--vault", str(self.vault), "--skip-secret-scan"])
        self.assertEqual(result.returncode, 0, msg=result.stderr + "\n" + result.stdout)
        # The remote should have received the new commit.
        remote_log = _git(self.remote, "log", "--oneline")
        self.assertIn("auto-sync", remote_log)

    # --- red validator path -------------------------------------------

    def test_red_validator_resets_index(self) -> None:
        _build_v4_vault(self.vault, validator=RED_VALIDATOR)
        _init_vault_git(self.vault, self.remote)
        (self.vault / "note.md").write_text("dirty", encoding="utf-8")
        # Snapshot the pre-call state of the staged index.
        before_status = _git(self.vault, "status", "--porcelain")
        before_log = _git(self.vault, "log", "--oneline")
        result = _run(["--vault", str(self.vault), "--skip-secret-scan"])
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("v4 validator refused", result.stderr)
        # Index is back to where it was before the call: a new file
        # in the working tree but nothing staged, and no new commit.
        after_status = _git(self.vault, "status", "--porcelain")
        after_log = _git(self.vault, "log", "--oneline")
        # The new file is still in the working tree (untracked); only
        # the staging area is empty.
        self.assertIn("note.md", after_status)
        self.assertFalse(
            any(line.startswith("A ") for line in after_status.splitlines()),
            "no path should be staged after a failed validator",
        )
        self.assertEqual(before_log, after_log)

    def test_no_validator_check_opt_in(self) -> None:
        # A red validator should still let the sync through when the
        # operator explicitly opts out. This is the only escape hatch.
        _build_v4_vault(self.vault, validator=RED_VALIDATOR)
        _init_vault_git(self.vault, self.remote)
        (self.vault / "note.md").write_text("hello", encoding="utf-8")
        result = _run(["--vault", str(self.vault), "--skip-secret-scan",
                       "--no-validator-check"])
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        remote_log = _git(self.remote, "log", "--oneline")
        self.assertIn("auto-sync", remote_log)

    # --- non-v4 path ---------------------------------------------------

    def test_non_v4_vault_unchanged(self) -> None:
        # A vault without _system/ must NOT trigger the v4 check.
        (self.vault / "INDEX.md").write_text("# v\n", encoding="utf-8")
        _init_vault_git(self.vault, self.remote)
        (self.vault / "note.md").write_text("hello", encoding="utf-8")
        result = _run(["--vault", str(self.vault), "--skip-secret-scan"])
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        remote_log = _git(self.remote, "log", "--oneline")
        self.assertIn("auto-sync", remote_log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
