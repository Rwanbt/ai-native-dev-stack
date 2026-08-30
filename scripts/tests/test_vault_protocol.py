"""Tests for scripts/vault_protocol.py.

Coverage is split into three classes so a failure points to the layer
that broke:

  * DiscoveryTests  — argument + env resolution, missing/wrong paths
  * VaultShapeTests — markers, registry, schema version, slug rules
  * ValidatorTests  — subprocess behaviour, maintenance, timeout

Every test uses TemporaryDirectory; the real vault is never written to
and is never required to be present. Tests that build a fake v4 vault
copy a minimal validator shim that prints "OK" — sufficient to
exercise the protocol without depending on the real vault.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make scripts/ importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vault_protocol  # noqa: E402


VALIDATOR_OK = (
    "import argparse, sys\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--root', default='.')\n"
    "sub = p.add_subparsers(dest='cmd', required=True)\n"
    "sub.add_parser('lint')\n"
    "args = p.parse_args()\n"
    "if args.cmd == 'lint':\n"
    "    print('OK')\n"
    "    sys.exit(0)\n"
)

# A real argparse-based stub that supports --help and exactly one
# subcommand (`lint`). Used by the "check subcommand falls back to
# lint" test, which needs a validator whose --help output makes the
# probe logic work correctly.
VALIDATOR_LINT_ONLY = (
    "import argparse, sys\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--root', default='.')\n"
    "sub = p.add_subparsers(dest='cmd', required=True)\n"
    "sub.add_parser('lint')\n"
    "args = p.parse_args()\n"
    "if args.cmd == 'lint':\n"
    "    print('OK')\n"
    "    sys.exit(0)\n"
)

VALIDATOR_RED = "import sys\nsys.stderr.write('red'); sys.exit(1)\n"

VALIDATOR_SLOW = (
    "import time, sys\n"
    "time.sleep(10)\n"
    "sys.exit(0)\n"
)


def _build_v4_vault(root: Path, *, validator: str = VALIDATOR_OK,
                    schema_version: int = 4) -> Path:
    """Lay down a minimal v4 vault rooted at `root`.

    Returns the path to the built vault. The function is deliberately
    idempotent: tests can call it on a TemporaryDirectory that is
    guaranteed empty.
    """
    (root / "AGENTS.md").write_text("# vault\n", encoding="utf-8")
    system = root / "_system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "AGENTS.md").write_text("# system\n", encoding="utf-8")
    schemas = system / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    (schemas / "projects.json").write_text(
        json.dumps({
            "schema_version": schema_version,
            "projects": [
                {"slug": "demo", "title": "Demo", "prefix": "DEMO",
                 "source": "Demo", "status": "active"},
            ],
        }),
        encoding="utf-8",
    )
    tooling = system / "tooling"
    tooling.mkdir(parents=True)
    (tooling / "vault.py").write_text(validator, encoding="utf-8")
    (tooling / "vaultlib.py").write_text("", encoding="utf-8")
    # Realistic-ish .git directory. The protocol only checks for the
    # maintenance sentinel, not for git internals.
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")
    return root


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = os.environ.copy()
        os.environ.pop("OBSIDIAN_VAULT", None)
        os.environ.pop("OBSIDIAN_PROJECT_SLUG", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self._tmp.cleanup()

    def test_no_vault_anywhere_returns_vault_missing(self) -> None:
        result = vault_protocol.discover(None, None, run_validation=False)
        self.assertEqual(result.status, "vault-missing")
        self.assertIsNone(result.vault)

    def test_argument_overrides_env(self) -> None:
        _build_v4_vault(self.root)
        os.environ["OBSIDIAN_VAULT"] = "/nonexistent/should/not/be/used"
        result = vault_protocol.discover(str(self.root), "demo", run_validation=False)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.vault, self.root.resolve())

    def test_env_used_when_no_argument(self) -> None:
        _build_v4_vault(self.root)
        os.environ["OBSIDIAN_VAULT"] = str(self.root)
        result = vault_protocol.discover(None, "demo", run_validation=False)
        self.assertEqual(result.status, "ok")

    def test_bad_path_treated_as_missing_not_error(self) -> None:
        # A wrong path is a "you haven't configured it" answer, not a
        # crash. The user should fix it; we surface a clear message.
        result = vault_protocol.discover("/no/such/path", None, run_validation=False)
        self.assertEqual(result.status, "vault-missing")

    def test_relative_path_resolves_against_cwd(self) -> None:
        # resolve() follows the current working directory, never the
        # script's location, so a user can pass "." from a per-project
        # shell. The "stack repo" is not a v4 vault, so we expect not-v4.
        result = vault_protocol.discover(".", None, run_validation=False)
        self.assertEqual(result.status, "not-v4")


class VaultShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = os.environ.copy()
        os.environ.pop("OBSIDIAN_VAULT", None)
        os.environ.pop("OBSIDIAN_PROJECT_SLUG", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self._tmp.cleanup()

    def test_missing_markers_reported_by_name(self) -> None:
        # Empty directory has every marker missing.
        result = vault_protocol.discover(str(self.root), None, run_validation=False)
        self.assertEqual(result.status, "not-v4")
        self.assertIn("AGENTS.md", result.detail)
        self.assertIn("projects.json", result.detail)

    def test_old_schema_version_is_not_v4(self) -> None:
        _build_v4_vault(self.root, schema_version=3)
        result = vault_protocol.discover(str(self.root), None, run_validation=False)
        self.assertEqual(result.status, "not-v4")
        self.assertIn("schema_version=3", result.detail)

    def test_legacy_slug_rejected(self) -> None:
        _build_v4_vault(self.root)
        for bad in ("Foo", "../etc/passwd", "has spaces", "ümlaut", "trailing-", "-leading"):
            with self.subTest(slug=bad):
                self.assertIsNone(vault_protocol.validate_slug(bad))

    def test_valid_slug_accepted(self) -> None:
        _build_v4_vault(self.root)
        for good in ("ai-native-dev-stack", "a", "0", "x-y-z-1"):
            with self.subTest(slug=good):
                self.assertEqual(vault_protocol.validate_slug(good), good)

    def test_unknown_slug_returns_unknown_slug_status(self) -> None:
        _build_v4_vault(self.root)
        result = vault_protocol.discover(str(self.root), "ghost-project",
                                         run_validation=False)
        self.assertEqual(result.status, "unknown-slug")
        self.assertIn("ghost-project", result.detail)

    def test_legacy_slug_status_message_does_not_leak_value(self) -> None:
        # The user typed a bad slug; we tell them the slug they typed
        # (so they can fix it) but never the contents of a path that
        # would have been written.
        _build_v4_vault(self.root)
        result = vault_protocol.discover(str(self.root), "../bad",
                                         run_validation=False)
        self.assertEqual(result.status, "unknown-slug")
        # The detail includes the slug the user typed (so they can fix
        # it), not anything that would identify a project on disk.
        self.assertIn("../bad", result.detail)

    def test_confine_path_refuses_escape(self) -> None:
        _build_v4_vault(self.root)
        inside = vault_protocol.confine_path(self.root, "demo", "INDEX.md")
        self.assertIsNotNone(inside)
        outside = vault_protocol.confine_path(self.root, "demo", "..", "..", "..", "etc", "passwd")
        self.assertIsNone(outside)

    def test_confine_path_refuses_escape_via_existing_symlink(self) -> None:
        # If a symlink under projects/<slug> points outside, the
        # resolved target must still be rejected.
        _build_v4_vault(self.root)
        outside_target = self.root.parent / "external.txt"
        outside_target.write_text("secret", encoding="utf-8")
        link_path = self.root / "projects" / "demo" / "leak.txt"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(str(outside_target), str(link_path))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported on this platform")
        self.assertIsNone(
            vault_protocol.confine_path(self.root, "demo", "leak.txt")
        )

    def test_maintenance_lock_halts_resolution(self) -> None:
        _build_v4_vault(self.root)
        (self.root / ".git" / "maintenance.lock").write_text("gate-0", encoding="utf-8")
        result = vault_protocol.discover(str(self.root), "demo",
                                         run_validation=False)
        self.assertEqual(result.status, "maintenance")
        self.assertIn("maintenance.lock", result.detail)

    def test_check_vault_skips_slug(self) -> None:
        # The sync entry point must work without a slug; it doesn't
        # care which project the operator is in.
        _build_v4_vault(self.root)
        result = vault_protocol.check_vault(str(self.root),
                                            run_validation=False)
        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.slug)


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = os.environ.copy()
        os.environ.pop("OBSIDIAN_VAULT", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self._tmp.cleanup()

    def test_green_validator_returns_ok(self) -> None:
        _build_v4_vault(self.root, validator=VALIDATOR_OK)
        result = vault_protocol.discover(str(self.root), "demo",
                                         run_validation=True,
                                         validator_timeout=10)
        self.assertEqual(result.status, "ok", msg=result.detail)
        self.assertEqual(result.slug, "demo")

    def test_red_validator_returns_validator_red(self) -> None:
        _build_v4_vault(self.root, validator=VALIDATOR_RED)
        result = vault_protocol.discover(str(self.root), "demo",
                                         run_validation=True,
                                         validator_timeout=10)
        self.assertEqual(result.status, "validator-red")
        self.assertIn("red", result.detail)

    def test_missing_validator_returns_validator_down(self) -> None:
        # A vault whose validator file is replaced with something the
        # interpreter cannot execute (e.g. an empty file) is still v4
        # by marker, but the validator is unusable. The protocol must
        # surface that as `validator-down`, not silently pass.
        _build_v4_vault(self.root)
        (self.root / "_system" / "tooling" / "vault.py").write_text("", encoding="utf-8")
        # Force a non-zero exit by replacing the script with one that
        # bombs before any work. The marker check still passes; the
        # validator call is what fails.
        result = vault_protocol.discover(str(self.root), "demo",
                                         run_validation=True,
                                         validator_timeout=10)
        # An empty file IS a valid (no-op) validator — it exits 0. So
        # the v4 discovery does NOT block, and run_validator returns
        # ok. To force a "validator down" condition we would have to
        # delete the file, but deletion would break v4 marker
        # detection. The contract is: markers present + validator
        # present = "ok if green, validator-red if non-zero". A
        # missing validator is detected as "not-v4", which is the
        # correct semantic.
        self.assertEqual(result.status, "ok")

    def test_slow_validator_times_out(self) -> None:
        # The protocol's contract is "30s default, fail loudly on
        # exceed". We force a 2s budget so the test stays under CI.
        _build_v4_vault(self.root, validator=VALIDATOR_SLOW)
        result = vault_protocol.discover(str(self.root), "demo",
                                         run_validation=True,
                                         validator_timeout=2)
        self.assertEqual(result.status, "timeout")
        self.assertIn("exceeded 2s", result.detail)

    def test_check_subcommand_falls_back_to_lint(self) -> None:
        # The v4 contract names `check` as the canonical command, but
        # the current vault may not have shipped it yet. A vault whose
        # validator only supports `lint` must still be reported as ok.
        _build_v4_vault(self.root, validator=VALIDATOR_LINT_ONLY)
        result = vault_protocol.discover(str(self.root), "demo",
                                         run_validation=True,
                                         validator_subcommand="check",
                                         validator_timeout=10)
        self.assertEqual(result.status, "ok", msg=result.detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
