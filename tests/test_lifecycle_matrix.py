"""The transition matrix, the round trips, and idempotence.

Every row of the matrix declared in the Distribution & Lifecycle plan is one
test here, and each asserts the observable end state rather than the return
value: an installer that reports success and wrote nothing must fail.
"""

from __future__ import annotations

import unittest

from tests.lifecycle_support import LifecycleTestCase
from ainative.lifecycle import planner as plannerlib
from ainative.lifecycle import state as statelib

STANDARD_MARKERS = ("AGENTS.md", "conventions.json", "tools/ai_docs/generate_all.py",
                    ".claude/skills/demo-skill/SKILL.md", ".agents/skills/demo-skill/SKILL.md")
VERIFIED_MARKERS = (".ai-native/lifecycle/verified.json",
                    ".ai-native/docs/VERIFIED-WORK-PLANE.md")


class TransitionMatrix(LifecycleTestCase):

    def assert_standard_installed(self) -> None:
        for marker in STANDARD_MARKERS:
            self.assertTrue(self.exists(marker), f"{marker} missing after a Standard install")
        self.assertEqual(self.state().active_profile, "standard")

    def assert_verified_installed(self) -> None:
        self.assert_verified_markers()
        self.assertEqual(self.state().active_profile, "verified")

    def assert_verified_markers(self) -> None:
        for marker in STANDARD_MARKERS + VERIFIED_MARKERS:
            self.assertTrue(self.exists(marker), f"{marker} missing after a Verified install")

    # --- none -> * -------------------------------------------------------

    def test_none_init_standard_installs_standard(self):
        result = self.install("standard")
        self.assertTrue(result.applied)
        self.assert_standard_installed()

    def test_none_init_verified_installs_verified(self):
        self.install("verified")
        self.assert_verified_installed()

    def test_verified_install_does_not_write_any_authority_artifact(self):
        self.install("verified")
        self.assertFalse(self.exists(".ai-native/trust/project_trust.json"),
                         "the installer fabricated a trust anchor")
        self.assertFalse(self.exists(".ai-native/work"), "the installer fabricated a work")
        marker = self.read(".ai-native/lifecycle/verified.json")
        self.assertIn("activation record only", marker)
        self.assertNotIn("trusted", marker)

    def test_verified_install_reports_the_bootstrap_is_still_required(self):
        result = self.install("verified")
        self.assertTrue(any("trust bootstrap" in notice for notice in result.notices),
                        f"no bootstrap notice in {result.notices}")

    # --- idempotence -----------------------------------------------------

    def test_second_init_standard_is_a_no_op(self):
        self.install("standard")
        again = self.install("standard")
        self.assertTrue(again.plan.is_noop, f"changes: {again.plan.counts()}")
        self.assertFalse(again.applied)

    def test_second_init_verified_is_a_no_op(self):
        self.install("verified")
        again = self.install("verified")
        self.assertTrue(again.plan.is_noop, f"changes: {again.plan.counts()}")

    def test_switch_to_the_active_profile_is_a_no_op(self):
        self.install("verified")
        self.assertTrue(self.switch("verified").plan.is_noop)

    def test_repair_on_a_healthy_install_changes_nothing(self):
        from ainative.lifecycle import recovery

        self.install("verified")
        before = self.read(".ai-native/lifecycle/state.json")
        result = recovery.repair(self.project, distribution=self.distribution,
                                 source=self.source)
        self.assertEqual(result.reinstalled, [])
        self.assertTrue(result.diagnosis.healthy, result.diagnosis.findings)
        self.assertEqual(before, self.read(".ai-native/lifecycle/state.json"))

    # --- standard <-> verified ------------------------------------------

    def test_standard_switch_verified_adds_only_the_delta(self):
        self.install("standard")
        result = self.switch("verified")
        created = [change.path for change in result.plan.mutating]
        self.assertEqual(sorted(created), sorted(VERIFIED_MARKERS))
        self.assert_verified_installed()

    def test_verified_switch_standard_preserves_the_audit_trail(self):
        self.install("verified")
        payloads = self.seed_verified_history()
        self.switch("standard")

        self.assertEqual(self.state().active_profile, "standard")
        for marker in VERIFIED_MARKERS:
            self.assertFalse(self.exists(marker), f"{marker} survived the downgrade")
        for relative, content in payloads.items():
            self.assertTrue(self.exists(relative), f"{relative} was destroyed")
            self.assertEqual(self.read(relative), content, f"{relative} was rewritten")

    def test_downgrade_reports_the_dormant_state_rather_than_hiding_it(self):
        self.install("verified")
        self.seed_verified_history()
        result = self.switch("standard")
        self.assertTrue(any("dormant" in notice for notice in result.notices),
                        f"no dormancy notice in {result.notices}")

    def test_switch_standard_never_removes_user_data(self):
        self.install("verified")
        self.seed_verified_history()
        plan = self.switch("standard", dry_run=True).plan
        removals = [c.path for c in plan.changes if c.action == plannerlib.REMOVE]
        for path in removals:
            self.assertFalse(path.startswith(".ai-native/trust"), path)
            self.assertFalse(path.startswith(".ai-native/work"), path)
            self.assertFalse(path.startswith(".ai-native/runs"), path)

    # --- round trips -----------------------------------------------------

    def test_round_trip_none_standard_verified_standard_verified(self):
        self.install("standard")
        self.write("mine/custom.txt", "user content\n")
        self.switch("verified")
        payloads = self.seed_verified_history()
        self.switch("standard")
        self.switch("verified")

        self.assert_verified_installed()
        self.assertEqual(self.read("mine/custom.txt"), "user content\n")
        for relative, content in payloads.items():
            self.assertEqual(self.read(relative), content,
                             f"{relative} did not survive the round trip byte for byte")

    def test_round_trip_none_standard_uninstall_standard(self):
        self.install("standard")
        self.uninstall()
        result = self.install("standard")
        self.assertTrue(result.applied)
        self.assert_standard_installed()

    def test_reinstall_verified_after_uninstall(self):
        self.install("verified")
        payloads = self.seed_verified_history()
        self.uninstall()
        self.install("verified")
        self.assert_verified_installed()
        for relative, content in payloads.items():
            self.assertEqual(self.read(relative), content)

    def test_a_stale_state_never_blocks_a_reinstall(self):
        self.install("verified")
        self.uninstall()
        state = self.state()
        self.assertIsNotNone(state)
        self.assertEqual(state.installed_components, [])
        self.assertTrue(self.install("standard").applied)
        self.assert_standard_installed()

    # --- uninstall -------------------------------------------------------

    def test_uninstall_removes_unchanged_managed_files_and_keeps_the_rest(self):
        self.install("standard")
        self.write("AGENTS.md", self.read("AGENTS.md") + "\n## my section\n")
        result = self.uninstall()

        self.assertFalse(self.exists(".claude/skills/demo-skill/SKILL.md"))
        self.assertIn("my section", self.read("AGENTS.md"))
        self.assertEqual(self.read("README.md"), "my project\n")
        self.assertIn("AGENTS.md", result.preserved_user_modified)

    def test_uninstall_preserves_verified_history(self):
        self.install("verified")
        payloads = self.seed_verified_history()
        self.uninstall()
        for relative, content in payloads.items():
            self.assertEqual(self.read(relative), content)

    def test_uninstall_purge_removes_verified_data_and_keeps_unrelated_files(self):
        self.install("verified")
        self.seed_verified_history()
        self.write("mine/notes.md", "unrelated\n")
        self.uninstall(purge=True, assume_yes=True)

        self.assertFalse(self.exists(".ai-native/trust/project_trust.json"))
        self.assertFalse(self.exists(".ai-native/work/w1/manifest.json"))
        self.assertTrue(self.exists("mine/notes.md"))
        self.assertEqual(self.read("README.md"), "my project\n")
        self.assertFalse(self.exists(".ai-native/lifecycle/state.json"))

    def test_purge_refuses_without_confirmation_when_there_is_no_terminal(self):
        from ainative.lifecycle.errors import LifecycleError

        self.install("verified")
        self.seed_verified_history()
        with self.assertRaises(LifecycleError) as raised:
            self.uninstall(purge=True)
        self.assertEqual(raised.exception.code, "CONFIRMATION_REQUIRED")
        self.assertTrue(self.exists(".ai-native/trust/project_trust.json"))

    def test_profile_purge_is_separate_from_switching(self):
        from ainative.lifecycle import uninstaller

        self.install("verified")
        self.seed_verified_history()
        self.switch("standard")
        self.assertTrue(self.exists(".ai-native/work/w1/manifest.json"))

        uninstaller.purge_profile(self.project, "verified", assume_yes=True,
                                  distribution=self.distribution)
        self.assertFalse(self.exists(".ai-native/work/w1/manifest.json"))
        self.assertTrue(self.exists("AGENTS.md"), "purging Verified took Standard with it")

    # --- dry run ---------------------------------------------------------

    def test_every_mutation_supports_dry_run_and_writes_nothing(self):
        from ainative.lifecycle import recovery, uninstaller

        before = sorted(p.relative_to(self.project).as_posix()
                        for p in self.project.rglob("*"))
        self.install("standard", dry_run=True)
        self.install("verified", dry_run=True)
        after = sorted(p.relative_to(self.project).as_posix()
                       for p in self.project.rglob("*"))
        self.assertEqual(before, after, "a dry run touched the filesystem")

        self.install("verified")
        snapshot = self._tree_digest()
        self.switch("standard", dry_run=True)
        self.switch("verified", dry_run=True)
        uninstaller.uninstall(self.project, dry_run=True, distribution=self.distribution)
        uninstaller.uninstall(self.project, purge=True, dry_run=True,
                              distribution=self.distribution)
        recovery.repair(self.project, dry_run=True, distribution=self.distribution)
        self.assertEqual(snapshot, self._tree_digest(), "a dry run mutated the project")

    def _tree_digest(self) -> list[tuple[str, str]]:
        from ainative.lifecycle.digest import digest_file

        return sorted((path.relative_to(self.project).as_posix(), digest_file(path) or "")
                      for path in self.project.rglob("*") if path.is_file())


if __name__ == "__main__":
    unittest.main()
