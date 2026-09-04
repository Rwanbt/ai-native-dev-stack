"""Interruption, rollback, recovery, locking, and legacy adoption.

The claim under test is the one ADR-0009 §4 makes: whatever happens, the project
ends in the old valid state or the new one. Interruptions are injected at the
four points the plan names — after the backup, after the first file, mid
external-config mutation, and immediately before the state is committed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase
from ainative.lifecycle import lock as locklib
from ainative.lifecycle import legacy as legacylib
from ainative.lifecycle import planner as plannerlib
from ainative.lifecycle import recovery, state as statelib
from ainative.lifecycle import transaction as txnlib
from ainative.lifecycle.errors import LifecycleError


class Interruption(Exception):
    """Stands in for a power cut at a chosen point in the apply loop."""


class _Interrupting(txnlib.Applier):
    """An applier that dies after N completed changes, or at the commit."""

    stop_after = None       # type: int | None
    stop_at_commit = False
    stop_on_block = False

    def _apply(self, change):
        if self.stop_on_block and change.action in (plannerlib.BLOCK_WRITE,
                                                    plannerlib.BLOCK_REMOVE):
            # Simulate dying *during* the external-config mutation: the journal
            # has the change, the file does not.
            self.journal.completed_changes.append(change.to_record())
            txnlib.write_journal(self.project, self.journal)
            raise Interruption("killed mid external-config mutation")
        super()._apply(change)
        if self.stop_after is not None and len(self.applied) >= self.stop_after:
            raise Interruption(f"killed after {self.stop_after} change(s)")

    def run(self, commit):
        if not self.stop_at_commit:
            return super().run(commit)

        def dying_commit():
            raise Interruption("killed before the state was committed")

        return super().run(dying_commit)


class TransactionSafety(LifecycleTestCase):

    def _plan(self, profile="standard"):
        from ainative.lifecycle import installer

        return installer.plan_profile(self.project, self.distribution, self.source,
                                      profile, operation="init")

    def _apply_interrupted(self, **attributes):
        plan, state, _ = self._plan()
        applier = _Interrupting(self.project, self.distribution, self.source, plan)
        for name, value in attributes.items():
            setattr(applier, name, value)
        with self.assertRaises(Interruption):
            applier.run(lambda: statelib.save(self.project, state))
        return applier

    def test_a_failure_after_the_backup_leaves_no_state_and_rolls_back(self):
        self._apply_interrupted(stop_after=1)
        self.assertIsNone(statelib.load(self.project),
                          "a state was committed for a transaction that failed")
        self.assertFalse(self.exists("AGENTS.md"))
        self.assertFalse(self.exists(".claude/skills/demo-skill/SKILL.md"))

    def test_a_failure_partway_through_removes_the_files_it_created(self):
        applier = self._apply_interrupted(stop_after=5)
        journal = txnlib.read_journals(self.project)[-1]
        self.assertEqual(journal.state, txnlib.ROLLED_BACK)
        for change in applier.plan.mutating[:5]:
            if change.action == plannerlib.CREATE:
                self.assertFalse(self.exists(change.path),
                                 f"{change.path} survived the rollback")

    def test_a_failure_at_commit_leaves_the_previous_valid_state(self):
        self.install("standard")
        before = self.read(".ai-native/lifecycle/state.json")
        self.write("AGENTS.md", "# edited so the next plan has work to do\n")

        plan, state, _ = self._plan("verified")
        applier = _Interrupting(self.project, self.distribution, self.source, plan)
        applier.stop_at_commit = True
        with self.assertRaises(Interruption):
            applier.run(lambda: statelib.save(self.project, state))

        self.assertEqual(self.read(".ai-native/lifecycle/state.json"), before,
                         "the state changed even though the commit failed")
        self.assertEqual(statelib.load(self.project).active_profile, "standard")

    def test_a_kill_partway_through_leaves_the_old_profile_recorded(self):
        """The ordering test: state committed last, not first.

        A process that is killed performs no rollback, and that is the case
        commit-last exists for — the state on disk must still describe the
        install that is actually there. Interrupting with an exception cannot
        show this any more, because the rollback path now restores the state
        too; so this models a kill by disabling the rollback.
        """

        from ainative.lifecycle import installer

        self.install("standard")
        self.assertEqual(statelib.load(self.project).active_profile, "standard")

        class KilledPartway(_Interrupting):
            stop_after = 1

            def rollback(self):
                return  # a killed process never gets here

        original = txnlib.Applier
        txnlib.Applier = KilledPartway
        self.addCleanup(setattr, txnlib, "Applier", original)
        with self.assertRaises(Interruption):
            installer.install(self.project, "verified", distribution=self.distribution,
                              source=self.source)

        current = statelib.load(self.project)
        self.assertEqual(current.active_profile, "standard",
                         "the state recorded the new profile for a transaction that "
                         "never finished")
        self.assertNotIn("verified-workplane", current.installed_components)

    def test_a_failure_partway_through_rolls_back_and_keeps_the_old_state(self):
        """The graceful path: an exception rolls files *and* state back."""

        from ainative.lifecycle import installer

        self.install("standard")
        before = self.read(".ai-native/lifecycle/state.json")

        class OneChangeThenDies(_Interrupting):
            stop_after = 1

        original = txnlib.Applier
        txnlib.Applier = OneChangeThenDies
        self.addCleanup(setattr, txnlib, "Applier", original)
        with self.assertRaises(Interruption):
            installer.install(self.project, "verified", distribution=self.distribution,
                              source=self.source)

        self.assertEqual(self.read(".ai-native/lifecycle/state.json"), before)
        self.assertFalse(self.exists(".ai-native/lifecycle/verified.json"))

    def test_an_interrupted_journal_is_detected_and_blocks_further_mutation(self):
        plan, _, _ = self._plan()
        applier = txnlib.Applier(self.project, self.distribution, self.source, plan)
        applier.journal.state = txnlib.APPLYING
        applier.journal.backup_location = "x"
        txnlib.write_journal(self.project, applier.journal)

        self.assertEqual(len(txnlib.interrupted(self.project)), 1)
        with self.assertRaises(LifecycleError) as raised:
            self.install("standard")
        self.assertEqual(raised.exception.code, "TRANSACTION_IN_PROGRESS")
        self.assertEqual(raised.exception.exit_code, 3)

    def test_no_mutation_runs_while_a_transaction_is_interrupted(self):
        """Every mutating entry point passes the same gate, purge included.

        `profile purge verified` was the one that did not, so the most
        destructive operation in the CLI ran on a project whose last
        transaction never finished (EMP-LC-016).
        """

        from ainative.lifecycle import uninstaller

        self.install("verified")
        self.seed_verified_history()
        journal = txnlib.Journal(identifier="txn_stuck", operation="update",
                                 from_profile="verified", to_profile="verified",
                                 state=txnlib.APPLYING)
        txnlib.write_journal(self.project, journal)

        for name, call in (
            ("init", lambda: self.install("verified")),
            ("switch", lambda: self.switch("standard")),
            ("uninstall", lambda: self.uninstall()),
            ("purge", lambda: uninstaller.purge_profile(
                self.project, "verified", assume_yes=True,
                distribution=self.distribution)),
        ):
            with self.subTest(operation=name):
                with self.assertRaises(LifecycleError) as raised:
                    call()
                self.assertEqual(raised.exception.code, "TRANSACTION_IN_PROGRESS")
                self.assertEqual(raised.exception.exit_code, 3)
        self.assertTrue(self.exists(".ai-native/work/w1/manifest.json"),
                        "a refused mutation destroyed data anyway")

    def test_repair_recovers_an_interrupted_transaction(self):
        self.install("standard")
        original = self.read("AGENTS.md")
        # Simulate a half-applied update: the file is replaced and backed up,
        # the journal says APPLYING, and the state was never committed.
        journal = txnlib.Journal(identifier="txn_test", operation="update",
                                 from_profile="standard", to_profile="standard",
                                 state=txnlib.APPLYING,
                                 backup_location=".ai-native/lifecycle/backups/txn_test")
        backup = self.project / journal.backup_location / "AGENTS.md"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(original, encoding="utf-8")
        journal.completed_changes = [{"action": "REPLACE", "path": "AGENTS.md",
                                      "component": "engineering-method",
                                      "ownership": "MANAGED_MUTABLE", "reason": "",
                                      "kind": "file"}]
        txnlib.write_journal(self.project, journal)
        self.write("AGENTS.md", "# half-written new version\n")

        result = recovery.repair(self.project, distribution=self.distribution,
                                 source=self.source)
        self.assertEqual(self.read("AGENTS.md"), original)
        self.assertEqual(txnlib.read_journals(self.project)[-1].effective_state,
                         txnlib.ROLLED_BACK)
        self.assertTrue(result.diagnosis.healthy, result.diagnosis.findings)

    def test_repair_restores_a_deleted_managed_file(self):
        self.install("standard")
        (self.project / ".claude/skills/demo-skill/SKILL.md").unlink()
        recovery.repair(self.project, distribution=self.distribution, source=self.source)
        self.assertTrue(self.exists(".claude/skills/demo-skill/SKILL.md"))

    def test_repair_never_overwrites_a_user_modified_file(self):
        self.install("standard")
        self.write("AGENTS.md", "# mine\n")
        (self.project / ".claude/skills/demo-skill/SKILL.md").unlink()
        result = recovery.repair(self.project, distribution=self.distribution,
                                 source=self.source)
        self.assertEqual(self.read("AGENTS.md"), "# mine\n")
        self.assertIn("AGENTS.md", result.preserved)

    def test_repair_quarantines_an_unreadable_state_without_losing_it(self):
        self.install("standard")
        (self.project / statelib.STATE_RELATIVE).write_text("{broken", encoding="utf-8")
        result = recovery.repair(self.project, distribution=self.distribution,
                                 source=self.source)
        quarantined = list((self.project / statelib.LIFECYCLE_DIRNAME)
                           .glob("state.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_text(encoding="utf-8"), "{broken")
        self.assertIn(statelib.STATE_RELATIVE.as_posix(), result.dropped)
        # And the project can be re-adopted afterwards.
        self.install("standard")
        self.assertTrue(self.exists("AGENTS.md"))

    def test_repair_drops_a_record_that_no_longer_resolves_inside_the_project(self):
        self.install("standard")
        path = self.project / statelib.STATE_RELATIVE
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["managed_files"].append({
            "path": "../outside.txt", "component": "engineering-method",
            "ownership": "MANAGED_IMMUTABLE", "digest_at_install": "0" * 64,
            "created_by_ainative": True, "kind": "file"})
        path.write_text(json.dumps(payload), encoding="utf-8")

        diagnosis = recovery.diagnose(self.project, distribution=self.distribution)
        self.assertFalse(diagnosis.healthy)
        recovery.repair(self.project, distribution=self.distribution, source=self.source)
        remaining = [entry.path for entry in statelib.load(self.project).managed_files]
        self.assertNotIn("../outside.txt", remaining)

    def test_backups_are_pruned_but_an_interrupted_one_is_kept(self):
        self.install("standard")
        for index in range(txnlib.RETENTION + 3):
            journal = txnlib.Journal(identifier=f"txn_{index:02d}", operation="noop",
                                     from_profile=None, to_profile=None,
                                     state=txnlib.COMMITTED, started_at=f"2026-01-{index+1:02d}")
            txnlib.write_journal(self.project, journal)
        stuck = txnlib.Journal(identifier="txn_stuck", operation="update", from_profile=None,
                               to_profile=None, state=txnlib.APPLYING,
                               started_at="2026-01-01")
        txnlib.write_journal(self.project, stuck)

        txnlib.prune(self.project)
        remaining = {item.identifier for item in txnlib.read_journals(self.project)}
        self.assertIn("txn_stuck", remaining, "an interrupted journal was pruned")
        self.assertLessEqual(len([n for n in remaining if n.startswith("txn_0")]),
                             txnlib.RETENTION + 1)


class Locking(LifecycleTestCase):

    def test_a_second_mutation_is_refused_while_one_holds_the_lock(self):
        (self.project / statelib.LIFECYCLE_DIRNAME).mkdir(parents=True, exist_ok=True)
        with locklib.acquire(self.project, "update"):
            with self.assertRaises(LifecycleError) as raised:
                with locklib.acquire(self.project, "uninstall"):
                    pass
        self.assertEqual(raised.exception.code, "LOCK_HELD")

    def test_the_lock_is_released_even_when_the_operation_raises(self):
        with self.assertRaises(ValueError):
            with locklib.acquire(self.project, "init"):
                raise ValueError("boom")
        self.assertFalse(locklib.lock_path(self.project).exists())

    def test_a_lock_owned_by_a_dead_process_is_reclaimed(self):
        path = locklib.lock_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        dead = self._dead_pid()
        path.write_text(json.dumps({"pid": dead, "operation": "update",
                                    "acquired_at": statelib.now(),
                                    "host": locklib._hostname()}), encoding="utf-8")
        with locklib.acquire(self.project, "init"):
            pass
        self.assertFalse(path.exists())

    def test_a_lock_owned_by_a_live_process_is_never_reclaimed(self):
        path = locklib.lock_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        child = subprocess.Popen([sys.executable, "-c",
                                  "import sys, time; sys.stdin.readline()"],
                                 stdin=subprocess.PIPE)
        self.addCleanup(child.kill)
        path.write_text(json.dumps({"pid": child.pid, "operation": "update",
                                    "acquired_at": statelib.now(),
                                    "host": locklib._hostname()}), encoding="utf-8")
        with self.assertRaises(LifecycleError) as raised:
            with locklib.acquire(self.project, "init"):
                pass
        self.assertEqual(raised.exception.code, "LOCK_HELD")
        self.assertTrue(path.exists(), "a live owner's lock was deleted")

    def test_a_lock_recorded_on_another_host_is_never_reclaimed(self):
        path = locklib.lock_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"pid": os.getpid(), "operation": "update",
                                    "acquired_at": statelib.now(),
                                    "host": "some-other-machine"}), encoding="utf-8")
        described = locklib.describe(self.project)
        self.assertIsNone(described["owner_alive"])
        with self.assertRaises(LifecycleError):
            with locklib.acquire(self.project, "init"):
                pass

    def test_force_unlock_takes_a_lock_a_human_declared_stale(self):
        path = locklib.lock_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"pid": os.getpid(), "operation": "update",
                                    "acquired_at": statelib.now(),
                                    "host": "some-other-machine"}), encoding="utf-8")
        with locklib.acquire(self.project, "init", force=True):
            pass

    def test_even_a_no_op_install_takes_the_lock_before_writing_state(self):
        """A no-op still commits the profile, and a commit is a write."""

        from ainative.lifecycle import installer
        from ainative.lifecycle.errors import LifecycleError

        self.install("standard")
        with locklib.acquire(self.project, "update"):
            with self.assertRaises(LifecycleError) as raised:
                installer.install(self.project, "verified", distribution=self.distribution,
                                  source=self.source, dry_run=False)
            self.assertIn(raised.exception.code, ("LOCK_HELD",))

    def test_concurrent_installs_do_not_interleave(self):
        outcomes: list[object] = []

        def worker():
            try:
                outcomes.append(self.install("standard"))
            except LifecycleError as error:
                outcomes.append(error)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertTrue(self.exists("AGENTS.md"))
        refusals = [item for item in outcomes if isinstance(item, LifecycleError)]
        for refusal in refusals:
            self.assertIn(refusal.code, ("LOCK_HELD", "TRANSACTION_IN_PROGRESS"))
        self.assertTrue(recovery.diagnose(self.project,
                                          distribution=self.distribution).healthy)

    @staticmethod
    def _dead_pid() -> int:
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        return child.pid


class LegacyAdoption(LifecycleTestCase):

    def _seed_legacy(self) -> None:
        """A project installed by the old install.py: real files, no state."""

        shutil.copytree(self.distribution_root / "tools" / "ai_docs",
                        self.project / "tools" / "ai_docs")
        for root in (".claude/skills", ".agents/skills"):
            shutil.copytree(self.distribution_root / "skills" / "demo-skill",
                            self.project / root / "demo-skill")
        shutil.copy2(self.distribution_root / "AGENTS.md", self.project / "AGENTS.md")
        self.write(".stack-lock.json", '{"tools": {}}')

    def test_a_legacy_install_is_detected(self):
        self._seed_legacy()
        self.assertTrue(legacylib.detect(self.project))
        self.assertFalse(statelib.exists(self.project))

    def test_adoption_claims_only_files_identical_to_what_is_shipped(self):
        self._seed_legacy()
        self.write("AGENTS.md", "# I customised this long ago\n")
        adoption = legacylib.adopt(self.project, self.distribution, self.source, "standard")

        by_path = {entry.path: entry for entry in adoption.adopted}
        self.assertEqual(by_path["tools/ai_docs/generate_all.py"].ownership,
                         "MANAGED_IMMUTABLE")
        self.assertEqual(by_path["AGENTS.md"].ownership, "MANAGED_MUTABLE",
                         "a customised file was claimed as immutable")
        self.assertIn("AGENTS.md", adoption.unmanaged)

    def test_init_adopts_a_legacy_install_without_overwriting_edits(self):
        self._seed_legacy()
        self.write("AGENTS.md", "# I customised this long ago\n")
        result = self.install("standard")

        self.assertEqual(self.read("AGENTS.md"), "# I customised this long ago\n")
        self.assertTrue(result.legacy.detected)
        self.assertTrue(any("Existing AI Native installation detected" in note
                            for note in result.notices))
        self.assertTrue(statelib.exists(self.project))

    def test_uninstalling_an_adopted_legacy_install_keeps_the_customised_file(self):
        self._seed_legacy()
        self.write("AGENTS.md", "# I customised this long ago\n")
        self.install("standard")
        self.uninstall()

        self.assertEqual(self.read("AGENTS.md"), "# I customised this long ago\n",
                         "adoption made the uninstaller delete a file it did not write")
        self.assertFalse(self.exists(".claude/skills/demo-skill/SKILL.md"))

    def test_a_clean_project_is_not_reported_as_legacy(self):
        adoption = legacylib.adopt(self.project, self.distribution, self.source, "standard")
        self.assertFalse(adoption.detected)


if __name__ == "__main__":
    unittest.main()
