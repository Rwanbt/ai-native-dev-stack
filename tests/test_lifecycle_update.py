"""Update detection, application, conflict handling, recovery and rollback.

Nothing here reaches the network. Two fixture distributions and a local
`UpdateProvider` exercise the same code path a real release takes — check,
fetch, digest, extract, plan, apply, roll back — so the update mechanism is
tested rather than the release process.
"""

from __future__ import annotations

import json
import unittest
from hashlib import sha256
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, build_distribution_tree, make_release_archive
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import state as statelib
from ainative.lifecycle import transaction as txnlib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle import version as versionlib
from ainative.lifecycle.errors import LifecycleError


class SemVer(unittest.TestCase):

    def test_string_ordering_does_not_decide_versions(self):
        self.assertTrue(versionlib.is_newer("1.10.0", "1.9.0"))
        self.assertFalse(versionlib.is_newer("1.9.0", "1.10.0"))
        self.assertTrue("1.10.0" < "1.9.0", "the string comparison is indeed wrong")

    def test_a_release_outranks_its_own_pre_release(self):
        self.assertTrue(versionlib.is_newer("1.0.0", "1.0.0-rc.1"))
        self.assertFalse(versionlib.is_newer("1.0.0-rc.1", "1.0.0"))
        self.assertTrue(versionlib.is_newer("1.0.0-rc.2", "1.0.0-rc.1"))

    def test_equal_versions_are_not_newer(self):
        self.assertFalse(versionlib.is_newer("2.3.4", "2.3.4"))

    def test_build_metadata_is_ignored_for_ordering(self):
        self.assertEqual(versionlib.compare("1.0.0+build1", "1.0.0+build2"), 0)

    def test_a_value_that_is_not_semver_is_refused_not_guessed(self):
        for candidate in ("", "latest", "1.2", "v1.2.3.4", "1.2.x"):
            with self.subTest(value=candidate):
                self.assertIsNone(versionlib.parse(candidate))
                self.assertFalse(versionlib.is_newer(candidate, "1.0.0"))


class LocalReleaseFixture(LifecycleTestCase):
    """A v1 install, and a v2 release published to a local directory."""

    def setUp(self) -> None:
        super().setUp()
        self.releases = self.root / "releases"
        self.releases.mkdir()
        self.v2_tree = build_distribution_tree(self.root / "dist-v2", "2.0.0")
        self.archive = make_release_archive(self.v2_tree, self.releases / "stack-2.0.0.zip")
        self.publish("2.0.0", self.archive)
        self.set_env(providerlib.PROVIDER_ENV, "local")
        self.set_env(providerlib.LOCAL_SOURCE_ENV, str(self.releases))

    def publish(self, version: str, archive: Path, digest: str | None = None) -> None:
        payload = {"channels": {"stable": {
            "version": version, "archive": archive.name,
            "sha256": digest if digest is not None
            else sha256(archive.read_bytes()).hexdigest(),
            "notes": f"release {version}"}}}
        (self.releases / "releases.json").write_text(json.dumps(payload), encoding="utf-8")


class UpdateCheck(LocalReleaseFixture):

    def test_a_newer_release_is_reported_as_available(self):
        self.install("standard")
        outcome = updaterlib.check(self.project, force=True)
        self.assertEqual(outcome.status, updaterlib.UPDATE_AVAILABLE)
        self.assertEqual(outcome.latest, "2.0.0")
        self.assertIn("2.0.0 is available", outcome.message())

    def test_the_same_version_produces_no_notification(self):
        self.install("standard")
        self.publish("1.0.0", self.archive)
        outcome = updaterlib.check(self.project, force=True)
        self.assertEqual(outcome.status, updaterlib.UP_TO_DATE)
        self.assertNotIn("available", outcome.message())

    def test_the_result_is_cached_and_the_cache_is_used(self):
        self.install("standard")
        updaterlib.check(self.project, force=True)
        self.assertTrue(updaterlib.cache_path(self.project).is_file())

        # Break the source: a cached answer must still be returned.
        (self.releases / "releases.json").unlink()
        cached = updaterlib.check(self.project)
        self.assertTrue(cached.from_cache)
        self.assertEqual(cached.latest, "2.0.0")

    def test_an_unreachable_source_is_offline_not_a_crash(self):
        self.install("standard")
        (self.releases / "releases.json").unlink()
        outcome = updaterlib.check(self.project, force=True)
        self.assertIn(outcome.status, (updaterlib.OFFLINE, updaterlib.CHECK_FAILED))
        self.assertIsNone(outcome.latest)

    def test_the_disable_variable_stops_every_network_check(self):
        self.install("standard")
        self.set_env(updaterlib.DISABLE_ENV, "1")
        outcome = updaterlib.check(self.project)
        self.assertEqual(outcome.status, updaterlib.DISABLED)
        self.assertFalse(updaterlib.cache_path(self.project).exists())

    def test_disabling_auto_check_in_preferences_stops_it_too(self):
        self.install("standard")
        state = statelib.load(self.project)
        state.update_preferences["auto_check"] = False
        statelib.save(self.project, state)
        self.assertEqual(updaterlib.check(self.project).status, updaterlib.DISABLED)

    def test_status_reads_the_cache_and_never_the_network(self):
        self.install("standard")
        updaterlib.check(self.project, force=True)
        (self.releases / "releases.json").unlink()
        notice = updaterlib.cached_notice(self.project)
        self.assertEqual(notice["latest"], "2.0.0")
        self.assertTrue(notice["from_cache"])

    def test_an_unknown_provider_name_is_refused(self):
        self.set_env(providerlib.PROVIDER_ENV, "carrier-pigeon")
        with self.assertRaises(LifecycleError):
            providerlib.build("stable")


class UpdateApply(LocalReleaseFixture):

    def test_standard_updates_to_the_new_release(self):
        self.install("standard")
        result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertTrue(result.applied)
        self.assertEqual(result.to_version, "2.0.0")
        self.assertEqual(self.read("AGENTS.md"), "# Engineering method 2.0.0\n")
        self.assertEqual(statelib.load(self.project).stack_version, "2.0.0")

    def test_verified_updates_and_keeps_its_history(self):
        self.install("verified")
        payloads = self.seed_verified_history()
        updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(statelib.load(self.project).active_profile, "verified")
        for relative, content in payloads.items():
            self.assertEqual(self.read(relative), content)

    def test_a_dry_run_update_writes_nothing(self):
        self.install("standard")
        before = self.read("AGENTS.md")
        result = updaterlib.apply(self.project, dry_run=True, distribution=self.distribution)
        self.assertFalse(result.applied)
        self.assertEqual(self.read("AGENTS.md"), before)

    def test_a_user_modified_file_survives_and_gets_the_new_one_beside_it(self):
        self.install("standard")
        self.write("AGENTS.md", "# mine\n")
        result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(self.read("AGENTS.md"), "# mine\n")
        self.assertIn("AGENTS.md", result.conflicts)
        self.assertEqual(self.read("AGENTS.md.new"), "# Engineering method 2.0.0\n")

    def test_a_tampered_archive_digest_stops_the_update_before_any_write(self):
        self.install("standard")
        self.publish("2.0.0", self.archive, digest="0" * 64)
        before = self.read("AGENTS.md")
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")
        self.assertEqual(self.read("AGENTS.md"), before)

    def test_an_update_with_nothing_newer_does_nothing(self):
        self.install("standard")
        self.publish("1.0.0", self.archive)
        result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertFalse(result.applied)

    def test_updating_a_project_that_was_never_installed_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "NOT_INSTALLED")


class UpdateRecovery(LocalReleaseFixture):

    def test_rollback_restores_the_previous_project_assets(self):
        self.install("standard")
        original = self.read("AGENTS.md")
        updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(self.read("AGENTS.md"), "# Engineering method 2.0.0\n")

        record = updaterlib.rollback(self.project)
        self.assertEqual(self.read("AGENTS.md"), original)
        self.assertEqual(statelib.load(self.project).stack_version, "1.0.0")
        self.assertIn("project assets", record["scope"])

    def test_rollback_dry_run_lists_without_restoring(self):
        self.install("standard")
        updaterlib.apply(self.project, distribution=self.distribution)
        record = updaterlib.rollback(self.project, dry_run=True)
        self.assertTrue(record["would_restore"])
        self.assertEqual(self.read("AGENTS.md"), "# Engineering method 2.0.0\n")

    def test_rollback_without_a_prior_update_is_refused_clearly(self):
        self.install("standard")
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.rollback(self.project)
        self.assertEqual(raised.exception.code, "ROLLBACK_UNAVAILABLE")

    def test_rollback_is_refused_when_the_backup_was_pruned(self):
        self.install("standard")
        updaterlib.apply(self.project, distribution=self.distribution)
        for journal in txnlib.read_journals(self.project):
            txnlib.journal_path(self.project, journal.identifier).unlink(missing_ok=True)
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.rollback(self.project)
        self.assertEqual(raised.exception.code, "ROLLBACK_UNAVAILABLE")

    def test_an_update_interrupted_before_commit_is_repaired_to_the_old_version(self):
        from ainative.lifecycle import installer, recovery

        self.install("standard")
        original = self.read("AGENTS.md")
        old_state = self.read(".ai-native/lifecycle/state.json")

        # Interrupt exactly where the plan says to: after the backup, after the
        # first file, and before the state was committed.
        source_v2 = self._staged_v2_source()
        plan, state, _ = installer.plan_profile(self.project, self.distribution, source_v2,
                                                "standard", operation="update")
        applier = txnlib.Applier(self.project, self.distribution, source_v2, plan)
        applier.journal.state = txnlib.APPLYING
        # `applier.project`, not `self.project`: the applier resolves the root
        # it is given, and on macOS the resolved form is a different string.
        applier.journal.backup_location = str(
            applier.backup_root.relative_to(applier.project).as_posix())
        txnlib.write_journal(self.project, applier.journal)
        first = plan.mutating[0]
        applier._apply(first)
        txnlib.write_journal(self.project, applier.journal)

        self.assertEqual(self.read(".ai-native/lifecycle/state.json"), old_state)
        self.assertEqual(len(txnlib.interrupted(self.project)), 1)

        recovery.repair(self.project, distribution=self.distribution, source=self.source)
        self.assertEqual(self.read("AGENTS.md"), original)
        self.assertEqual(statelib.load(self.project).stack_version, "1.0.0")
        self.assertEqual(txnlib.interrupted(self.project), [])

    def _staged_v2_source(self):
        from ainative.lifecycle import source as sourcelib

        return sourcelib.DistributionSource(root=self.v2_tree.resolve(), origin="test",
                                            version="2.0.0")


if __name__ == "__main__":
    unittest.main()
