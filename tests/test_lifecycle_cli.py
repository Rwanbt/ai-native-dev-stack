"""The CLI contract: exit codes, JSON, no-TTY behaviour, and the layer boundary.

Two things are proved here that no other suite can prove. First, the commands
behave the same without a terminal — a CI that blocks on `Are you sure? [y/N]`
is a broken product. Second, the dependency direction ADR-0009 §1 declares is
real: the Standard lifecycle does not load an authority module, the Work Plane
does not load the lifecycle, and an authority command reaches no network.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, REPO
from ainative.lifecycle.errors import (EXIT_FAILED, EXIT_INVALID_REQUEST, EXIT_OK,
                                       EXIT_RECOVERY_REQUIRED, ERROR_EXIT_CODES)


class ExitCodesAndJson(LifecycleTestCase):

    def test_init_status_and_uninstall_round_trip_through_the_console_entry_point(self):
        self.assertEqual(self.cli("init", "--profile", "standard").returncode, EXIT_OK)
        status = self.cli("status", "--json")
        self.assertEqual(status.returncode, EXIT_OK)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["profile"], "standard")
        self.assertTrue(payload["lifecycle"]["healthy"])
        self.assertEqual(self.cli("uninstall").returncode, EXIT_OK)

    def test_every_documented_command_emits_parseable_json(self):
        self.cli("init", "--profile", "verified")
        for command in (("status", "--json"), ("profile", "status", "--json"),
                        ("doctor", "--json"), ("update", "check", "--json"),
                        ("uninstall", "--dry-run", "--json"),
                        ("init", "--profile", "verified", "--dry-run", "--json"),
                        ("profile", "switch", "standard", "--dry-run", "--json"),
                        ("repair", "--dry-run", "--json")):
            with self.subTest(command=command):
                completed = self.cli(*command)
                try:
                    json.loads(completed.stdout)
                except ValueError as error:
                    self.fail(f"{command} did not emit JSON: {error}\n{completed.stdout[:400]}"
                              f"\n{completed.stderr[:400]}")

    def test_an_unknown_profile_exits_two_and_names_the_known_ones(self):
        completed = self.cli("init", "--profile", "platinum")
        self.assertEqual(completed.returncode, EXIT_INVALID_REQUEST)

    def test_purge_without_yes_and_without_a_tty_refuses_rather_than_prompting(self):
        self.cli("init", "--profile", "verified")
        self.seed_verified_history()
        completed = self.cli("uninstall", "--purge")
        self.assertEqual(completed.returncode, EXIT_INVALID_REQUEST)
        self.assertIn("CONFIRMATION_REQUIRED", completed.stderr)
        self.assertTrue(self.exists(".ai-native/trust/project_trust.json"))

    def test_purge_with_yes_succeeds_without_a_tty(self):
        self.cli("init", "--profile", "verified")
        self.seed_verified_history()
        completed = self.cli("uninstall", "--purge", "--yes")
        self.assertEqual(completed.returncode, EXIT_OK)
        self.assertFalse(self.exists(".ai-native/trust/project_trust.json"))

    def test_init_without_a_profile_and_without_a_tty_refuses_with_guidance(self):
        completed = self.cli("init")
        self.assertEqual(completed.returncode, EXIT_INVALID_REQUEST)
        self.assertIn("--profile standard", completed.stderr)

    def test_an_interrupted_transaction_makes_a_mutation_exit_three(self):
        from ainative.lifecycle import transaction as txnlib

        self.cli("init", "--profile", "standard")
        journal = txnlib.Journal(identifier="txn_stuck", operation="update",
                                 from_profile="standard", to_profile="standard",
                                 state=txnlib.APPLYING)
        txnlib.write_journal(self.project, journal)
        completed = self.cli("init", "--profile", "standard")
        self.assertEqual(completed.returncode, EXIT_RECOVERY_REQUIRED)

    def test_doctor_exits_one_when_the_install_is_not_healthy(self):
        self.cli("init", "--profile", "standard")
        (self.project / "AGENTS.md").unlink()
        self.assertEqual(self.cli("doctor").returncode, EXIT_FAILED)
        self.assertEqual(self.cli("repair").returncode, EXIT_OK)
        self.assertEqual(self.cli("doctor").returncode, EXIT_OK)

    def test_a_healthy_verified_install_exits_zero_from_status(self):
        self.cli("init", "--profile", "verified")
        completed = self.cli("status")
        self.assertEqual(completed.returncode, EXIT_OK, completed.stdout)

    def test_every_declared_error_code_maps_to_a_documented_exit_code(self):
        for code, value in ERROR_EXIT_CODES.items():
            with self.subTest(code=code):
                self.assertIn(value, (EXIT_FAILED, EXIT_INVALID_REQUEST,
                                      EXIT_RECOVERY_REQUIRED))

    def test_version_reports_three_independent_numbers(self):
        completed = self.cli_bare("--version")
        self.assertEqual(completed.returncode, EXIT_OK)
        for label in ("lifecycle:", "state_schema:", "stack:", "workplane_runtime:"):
            self.assertIn(label, completed.stdout)


class VerifiedCommandsStillWork(LifecycleTestCase):

    def _workplane(self, *args: str) -> subprocess.CompletedProcess:
        import os

        environment = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8"}
        return subprocess.run([sys.executable, "-m", "ainative.cli", *args],
                              capture_output=True, text=True, env=environment, cwd=str(REPO))

    def test_the_five_verified_entry_points_are_reachable_through_the_dispatcher(self):
        for command in ("trust", "work", "verify", "converge", "debug"):
            with self.subTest(command=command):
                completed = self._workplane(command, "--help")
                self.assertEqual(completed.returncode, EXIT_OK, completed.stderr[:400])

    def test_the_dispatcher_does_not_reinterpret_a_work_plane_refusal(self):
        # `work validate` on a path that holds no contract: the Work Plane's own
        # refusal and its exit code 2, not a lifecycle error.
        completed = self._workplane("work", "validate", str(self.project))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("refused:", completed.stderr)

    def test_converge_help_matches_the_work_plane_parser(self):
        from ainative_workplane.cli import build_parser

        self.assertIn("converge", build_parser().format_help())


class LayerBoundary(unittest.TestCase):
    """The dependency direction, proved by what actually gets imported."""

    def _modules_after(self, statement: str) -> set[str]:
        import os

        script = (f"import sys\n{statement}\n"
                  "print('\\n'.join(sorted(m for m in sys.modules "
                  "if m.startswith('ainative'))))\n")
        completed = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                   text=True, cwd=str(REPO),
                                   env={**os.environ, "PYTHONPATH": str(REPO)})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return set(completed.stdout.split())

    def test_the_lifecycle_layer_never_imports_the_work_plane(self):
        loaded = self._modules_after(
            "import ainative.lifecycle.installer, ainative.lifecycle.uninstaller, "
            "ainative.lifecycle.updater, ainative.lifecycle.recovery, "
            "ainative.lifecycle.status")
        offenders = {name for name in loaded if name.startswith("ainative_workplane")}
        self.assertEqual(offenders, set(),
                         f"the lifecycle layer pulled in the Work Plane: {offenders}")

    def test_the_work_plane_never_imports_the_lifecycle_layer(self):
        loaded = self._modules_after("import ainative_workplane")
        offenders = {name for name in loaded
                     if name == "ainative" or name.startswith("ainative.")}
        self.assertEqual(offenders, set(),
                         f"the Work Plane pulled in the lifecycle layer: {offenders}")

    def test_no_work_plane_module_mentions_the_lifecycle_package(self):
        package = REPO / "ainative_workplane"
        for path in sorted(package.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("from ainative.", text, path.name)
            self.assertNotIn("import ainative.", text, path.name)

    def test_the_trust_anchor_path_mirrored_by_the_installer_is_the_real_one(self):
        from ainative.lifecycle.installer import TRUST_ANCHOR_RELATIVE
        from ainative_workplane.bootstrap import TRUST_RELATIVE

        self.assertEqual(TRUST_ANCHOR_RELATIVE, TRUST_RELATIVE.as_posix(),
                         "the mirrored trust path drifted from the Work Plane's")


class AuthorityCommandsDoNoNetwork(LifecycleTestCase):

    def test_a_verified_command_never_triggers_an_update_check(self):
        """Break the network, then run the authority surface. It must not notice."""

        import urllib.request

        from ainative import cli as clilib

        calls: list[str] = []

        def refuse(*args, **kwargs):
            calls.append("urlopen")
            raise AssertionError("an authority command reached the network")

        original = urllib.request.urlopen
        urllib.request.urlopen = refuse
        self.addCleanup(setattr, urllib.request, "urlopen", original)

        for command in (["trust", "show", "--repo", str(self.project)],
                        ["work", "--help"], ["converge", "--help"]):
            with self.subTest(command=command[0]):
                try:
                    clilib.main(command)
                except SystemExit:
                    pass
        self.assertEqual(calls, [])

    def test_the_updater_is_not_reachable_from_the_verified_branch(self):
        source = (REPO / "ainative" / "cli.py").read_text(encoding="utf-8")
        verified_branch = source[source.index("if arguments and arguments[0] in VERIFIED"):]
        handover = verified_branch[:verified_branch.index("parser = build_parser()")]
        self.assertNotIn("updater", handover)
        self.assertNotIn("check(", handover)


if __name__ == "__main__":
    unittest.main()
