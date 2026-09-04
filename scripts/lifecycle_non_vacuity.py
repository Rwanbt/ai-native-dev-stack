#!/usr/bin/env python3
"""Prove each lifecycle guard actually blocks something.

A test that passes because the situation it describes cannot arise is not
evidence. So for every protection that matters, this script removes the guard in
a scratch copy of the repository and asserts that the matching test then FAILS.
A guard whose removal changes nothing was never doing anything.

The repository itself is never modified: everything happens in a temporary copy
which is deleted afterwards.

Usage:
    python scripts/lifecycle_non_vacuity.py            # all cases
    python scripts/lifecycle_non_vacuity.py --case ownership_prune
    python scripts/lifecycle_non_vacuity.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COPIED = ("ainative", "ainative_workplane", "tests", "skills", "tools", "templates",
          "docs", "scripts")
COPIED_FILES = ("AGENTS.md", "VERSION", "conventions.json")
TEST_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class Edit:
    """One exact substitution in one file."""

    file: str
    find: str
    replace: str


@dataclass(frozen=True)
class Case:
    """One guard, the edits that remove it, and the test that must then fail.

    Several edits per case on purpose. Where a protection is layered, removing
    one layer proves nothing — the next layer still refuses, and the case would
    be measuring redundancy instead of necessity. Two cases here needed a second
    edit for exactly that reason, and both were reported VACUOUS until they got
    it: the archive extraction and the downgrade preservation.
    """

    name: str
    guards: str
    edits: tuple
    test: str


CASES = (
    Case(
        name="ownership_uninstall",
        guards="an uninstall must not remove a managed file the user edited",
        edits=(Edit("ainative/lifecycle/digest.py",
                    "    return status == UNCHANGED\n",
                    "    return status in (UNCHANGED, USER_MODIFIED, MISSING)\n"),),
        test=("tests.test_lifecycle_ownership.ManagedFileOwnership"
              ".test_a_user_edited_managed_file_is_never_removed_by_an_uninstall"),
    ),
    Case(
        name="ownership_replace",
        guards="an install must not overwrite a managed file the user edited",
        edits=(Edit("ainative/lifecycle/digest.py",
                    "    return status in (UNCHANGED, MISSING)\n",
                    "    return True\n"),),
        test=("tests.test_lifecycle_ownership.ManagedFileOwnership"
              ".test_a_user_edited_managed_file_is_never_replaced_by_an_install"),
    ),
    Case(
        name="ownership_prune",
        guards="pruning a file removed upstream must skip one the user edited",
        edits=(Edit("ainative/lifecycle/planner.py",
                    "        elif digestlib.is_safe_to_remove(status):\n",
                    "        elif True:\n"),),
        test=("tests.test_lifecycle_ownership.ManagedFileOwnership"
              ".test_a_file_the_upstream_dropped_is_pruned_only_when_unchanged"),
    ),
    Case(
        name="legacy_adoption",
        guards="adoption must not let an install overwrite a customised file",
        edits=(Edit("ainative/lifecycle/legacy.py",
                    "                                       manifestlib.MANAGED_MUTABLE, current,\n"
                    "                                       created_by_ainative=False))\n",
                    "                                       manifestlib.MANAGED_MUTABLE, current,\n"
                    "                                       created_by_ainative=True))\n"),),
        test=("tests.test_lifecycle_transactions.LegacyAdoption"
              ".test_init_adopts_a_legacy_install_without_overwriting_edits"),
    ),
    Case(
        name="path_traversal",
        guards="a manifest or state path must not escape the project root",
        edits=(Edit("ainative/lifecycle/paths.py",
                    "    for part in posix.parts:\n"
                    "        if part in _RESERVED_COMPONENTS or part.strip() != part:\n"
                    '            raise _reject(relative, f"illegal component {part!r}")\n',
                    "    for part in posix.parts:\n        pass\n"),),
        test=("tests.test_lifecycle_security.PathContainment"
              ".test_every_traversal_shape_is_refused"),
    ),
    Case(
        name="archive_traversal",
        guards="a release archive entry must not extract outside the staging root",
        # Two layers: the pre-scan that refuses the archive before extraction,
        # and the per-entry containment that builds each target path.
        edits=(Edit("ainative/lifecycle/updater.py",
                    "            validate_relative(name)"
                    "          # refuses .., absolute, drive, NUL\n",
                    "            pass\n"),
               Edit("ainative/lifecycle/updater.py",
                    "            target = root.joinpath(*validate_relative(info.filename).parts)\n",
                    "            target = root / info.filename\n")),
        test=("tests.test_lifecycle_security.UpdateArchiveSafety"
              ".test_an_archive_naming_a_traversal_path_is_refused_before_extraction"),
    ),
    Case(
        name="archive_digest",
        guards="a release archive whose digest does not match must not be applied",
        edits=(Edit("ainative/lifecycle/provider.py",
                    "    if expected and actual.lower() != expected.lower():\n",
                    "    if False:\n"),),
        test=("tests.test_lifecycle_update.UpdateApply"
              ".test_a_tampered_archive_digest_stops_the_update_before_any_write"),
    ),
    Case(
        name="commit_state_last",
        guards="the install state must be committed after every change, never before",
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "            for change in self.plan.mutating:\n"
                    "                self._apply(change)\n"
                    "            self._verify()\n"
                    "            commit()   # the install state is written here, and only here\n",
                    "            commit()\n"
                    "            for change in self.plan.mutating:\n"
                    "                self._apply(change)\n"
                    "            self._verify()\n"),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_a_kill_partway_through_leaves_the_old_profile_recorded"),
    ),
    Case(
        name="rollback_completeness",
        guards="reversing an update must remove what it created, not only restore "
               "what it replaced",
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "        elif record.get(\"action\") == plannerlib.CREATE and target.is_file():\n"
                    "            # Created by this transaction, so there is nothing to restore: the\n"
                    "            # previous state did not have it. Leaving it behind is what made\n"
                    "            # `update rollback` produce a v1 project holding v2's new files.\n"
                    "            target.unlink(missing_ok=True)\n"
                    "            removed.append(path)\n",
                    "        elif False:\n            pass\n"),),
        test=("tests.test_lifecycle_update.UpdateRecovery"
              ".test_rollback_also_removes_the_files_the_update_created"),
    ),
    Case(
        name="purge_respects_user_edits",
        guards="--purge must not delete a managed file the user edited",
        edits=(Edit("ainative/lifecycle/planner.py",
                    "    if digestlib.is_safe_to_remove(status):\n"
                    "        return Change(REMOVE, entry.path, entry.component, entry.ownership,\n"
                    "                      f\"unchanged since install{suffix}\")\n",
                    "    if purge or digestlib.is_safe_to_remove(status):\n"
                    "        return Change(REMOVE, entry.path, entry.component, entry.ownership,\n"
                    "                      f\"unchanged since install{suffix}\")\n"),),
        test=("tests.test_lifecycle_matrix.TransitionMatrix"
              ".test_purge_still_keeps_a_managed_file_the_user_edited"),
    ),
    Case(
        name="orphan_respects_user_edits",
        guards="the orphaned-record path must decide removals the same way as "
               "every other path",
        edits=(Edit("ainative/lifecycle/planner.py",
                    "            plan.changes.append(removal_change(project, entry, purge=purge,\n"
                    "                                               note=\"orphaned record\"))\n",
                    "            _s = digestlib.classify(resolve_within(project, entry.path),\n"
                    "                                    entry.digest_at_install)\n"
                    "            plan.changes.append(Change(\n"
                    "                REMOVE if (purge or digestlib.is_safe_to_remove(_s)) "
                    "else PRESERVE,\n"
                    "                entry.path, entry.component, entry.ownership,\n"
                    "                \"orphaned managed file\", kind=entry.kind))\n"),),
        test=("tests.test_lifecycle_matrix.TransitionMatrix"
              ".test_purge_after_a_plain_uninstall_still_keeps_a_user_edited_file"),
    ),
    Case(
        name="dry_run_update_writes_nothing",
        guards="a dry-run update must not write a conflict file or a cache entry",
        # Two halves, because the test asserts both: the conflict file is
        # written before the dry-run check again, and the check records its
        # answer to the cache again.
        edits=(Edit("ainative/lifecycle/updater.py",
                    "        if dry_run:\n"
                    "            return UpdateResult(False, True, state.stack_version, "
                    "staged_source.version,\n"
                    "                                outcome, plan.to_record(), conflicts)\n",
                    "        for path in conflicts:\n"
                    "            _write_side_by_side(project, plan, staged_source, path)\n"
                    "        if dry_run:\n"
                    "            return UpdateResult(False, True, state.stack_version, "
                    "staged_source.version,\n"
                    "                                outcome, plan.to_record(), conflicts)\n"),
               Edit("ainative/lifecycle/updater.py",
                    "    outcome = check(project, force=True, record=not dry_run, state=state)\n",
                    "    outcome = check(project, force=True, state=state)\n")),
        test=("tests.test_lifecycle_update.UpdateApply"
              ".test_a_dry_run_update_writes_nothing"),
    ),
    Case(
        name="ownership_flag_typing",
        guards="a non-boolean ownership flag must preserve, not delete",
        edits=(Edit("ainative/lifecycle/state.py",
                    "            created_by_ainative=created if isinstance(created, bool) "
                    "else False,\n",
                    "            created_by_ainative=bool(created),\n"),),
        test=("tests.test_lifecycle_security.CorruptState"
              ".test_a_non_boolean_ownership_flag_preserves_rather_than_deletes"),
    ),
    Case(
        name="journal_durability",
        guards="a killed transaction must leave a journal that can be recovered from",
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "        self.journal.completed_changes.append(record)\n"
                    "        write_journal(self.project, self.journal)\n",
                    "        self.journal.completed_changes.append(record)\n"),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_a_killed_transaction_persists_what_it_had_already_applied"),
    ),
    Case(
        name="crlf_preservation",
        guards="an external config file must keep its own line endings",
        edits=(Edit("ainative/lifecycle/external.py",
                    '        with path.open("r", encoding="utf-8", newline="") as handle:\n'
                    "            return handle.read()\n",
                    '        return path.read_text(encoding="utf-8")\n'),),
        test=("tests.test_lifecycle_ownership.ExternalConfiguration"
              ".test_a_crlf_file_keeps_its_line_endings"),
    ),
    Case(
        name="lock_atomicity",
        guards="a lock being written must not be mistaken for an invalid one",
        edits=(Edit("ainative/lifecycle/lock.py",
                    "        if existing is None:\n"
                    "            # Unreadable. That is either corruption or a claim being made "
                    "right\n"
                    "            # now, and this code cannot tell them apart — so it refuses "
                    "rather\n"
                    "            # than deleting what may be a live owner's lock.\n"
                    "            raise LifecycleError(\n"
                    '                "LOCK_HELD",\n'
                    '                f"{path} exists but cannot be read as a lock. If no '
                    'lifecycle "\n'
                    '                "operation is running, re-run with --force-unlock.")\n',
                    "        if existing is None:\n"
                    "            path.unlink(missing_ok=True)\n"
                    "            continue\n"),),
        test=("tests.test_lifecycle_transactions.Locking"
              ".test_a_lock_being_written_is_not_treated_as_invalid"),
    ),
    Case(
        name="undo_respects_a_later_edit",
        guards="an undo must not overwrite a file edited after the interruption",
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "        if not _still_ours(target, record):""\n"
                    "            conflicts.append(path)""\n"
                    "            continue""\n",
                    "        if False:""\n"
                    "            conflicts.append(path)""\n"
                    "            continue" + '\\n'),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_repair_leaves_a_file_the_user_fixed_after_the_interruption"),
    ),
    Case(
        name="rollback_follows_the_journal",
        guards="a rollback must cover a change that was written and then raised",
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "        undo(self.project, self.journal)""\n",
                    "        for change, target in reversed(self.applied):""\n"
                    "            try:""\n"
                    "                self._restore(change, target)""\n"
                    "            except OSError:""\n"
                    "                continue""\n"
                    "        restore_install_state(self.project, self.journal)""\n"
                    "        self.journal.state = ROLLED_BACK""\n"
                    "        write_journal(self.project, self.journal)" + '\\n'),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_a_write_that_raises_after_landing_is_still_rolled_back"),
    ),
    Case(
        name="marker_is_a_whole_line",
        guards="a line that only starts like a marker must not open a region",
        edits=(Edit("ainative/lifecycle/external.py",
                    '    return "(?m)^" + re.escape(marker) + _LINE_END'"\n",
                    '    return "(?m)^" + re.escape(marker)' + '\\n'),),
        test=("tests.test_lifecycle_ownership.ExternalConfiguration"
              ".test_a_line_that_only_starts_like_a_marker_is_not_one"),
    ),
    Case(
        name="conflict_file_after_apply",
        guards="a .new file must not survive an update that failed",
        # Move the write back before the install, in two steps: take it out of
        # its current place first, then put it back ahead of the transaction.
        # Removing it outright would be vacuous — no `.new` at all also leaves
        # none behind.
        edits=(Edit("ainative/lifecycle/updater.py",
                    '        side_by_side = [name for name in\n',
                    '        _early = [name for name in\n'),
               Edit("ainative/lifecycle/updater.py",
                    '        result = installerlib.install(project, state.active_profile, '
                    'operation="update",\n',
                    '        side_by_side = [name for name in\n'
                    '                        (_write_side_by_side(project, plan, '
                    'staged_source, path,\n'
                    '                                             staged_source.version)\n'
                    '                         for path in conflicts) if name]\n'
                    '        result = installerlib.install(project, state.active_profile, '
                    'operation="update",\n')),
        test=("tests.test_lifecycle_update.UpdateApply"
              ".test_a_conflict_file_is_written_only_after_the_update_applies"),
    ),
    Case(
        name="lock_release_is_owned",
        guards="releasing a lock must not remove one that now belongs to someone else",
        edits=(Edit("ainative/lifecycle/lock.py",
                    "                _release(project, info)""\n",
                    "                path.unlink(missing_ok=True)" + '\\n'),),
        test=("tests.test_lifecycle_transactions.Locking"
              ".test_force_unlock_does_not_make_the_old_owner_delete_the_new_lock"),
    ),
    Case(
        name="new_file_never_overwritten",
        guards="an existing .new file must not be overwritten by an update",
        edits=(Edit("ainative/lifecycle/updater.py",
                    "        for candidate in _side_by_side_names(path, version):\n"
                    "            target = project / candidate\n"
                    "            if not target.exists():\n"
                    "                statelib.write_bytes_atomic(target, payload)\n"
                    "                return candidate\n"
                    "        return None\n",
                    '        statelib.write_bytes_atomic(project / f"{path}.new", payload)\n'
                    '        return f"{path}.new"\n'),),
        test=("tests.test_lifecycle_update.UpdateApply"
              ".test_an_existing_new_file_is_never_overwritten"),
    ),
    Case(
        name="undo_bounded_by_the_plan",
        guards="an undo must not act on a path the plan never named",
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "        if planned and path not in planned:\n"
                    "            conflicts.append(path)\n"
                    "            continue\n",
                    "        if False:\n"
                    "            conflicts.append(path)\n"
                    "            continue\n"),),
        test=("tests.test_lifecycle_security.TamperedJournal"
              ".test_a_completed_change_the_plan_never_named_is_refused"),
    ),
    Case(
        name="repair_archives_the_state",
        guards="repair must keep a copy of the install state it rewrites",
        edits=(Edit("ainative/lifecycle/recovery.py",
                    "            _archive_state(project)\n",
                    "            pass\n"),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_repair_keeps_a_copy_of_the_state_it_rewrites"),
    ),
    Case(
        name="force_unlock_reports_refusals",
        guards="a refused unlink under --force-unlock must be a lifecycle error",
        edits=(Edit("ainative/lifecycle/lock.py",
                    "            try:\n"
                    "                path.unlink(missing_ok=True)\n"
                    "            except OSError as error:\n",
                    "            if True:\n"
                    "                path.unlink(missing_ok=True)\n"
                    "            elif False:\n"),),
        test=("tests.test_lifecycle_transactions.Locking"
              ".test_force_unlock_reports_a_refused_unlink_instead_of_a_traceback"),
    ),
    Case(
        name="journal_id_containment",
        guards="a tampered transaction journal must not write outside the project",
        # Three layers: the id checked on read, the id checked on write, and
        # the backup location. Any one of them refuses the tampered journal, so
        # a case that removes fewer measures redundancy instead of necessity.
        edits=(Edit("ainative/lifecycle/transaction.py",
                    "        if not _JOURNAL_ID.match(identifier):\n",
                    "        if False:\n"),
               Edit("ainative/lifecycle/transaction.py",
                    "    if not _JOURNAL_ID.match(journal.identifier):\n",
                    "    if False:\n"),
               Edit("ainative/lifecycle/transaction.py",
                    "            validate_relative(location)"
                    "      # refuses .., absolute, drive, UNC, NUL\n",
                    "            pass\n")),
        test=("tests.test_lifecycle_security.TamperedJournal"
              ".test_a_journal_id_that_escapes_cannot_make_repair_write_outside"),
    ),
    Case(
        name="purge_recovery_gate",
        guards="purging user data must refuse while a transaction is unrecovered",
        edits=(Edit("ainative/lifecycle/uninstaller.py",
                    "    pending = txnlib.interrupted(project)\n    if pending and not dry_run:\n",
                    "    pending = txnlib.interrupted(project)\n    if False:\n"),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_no_mutation_runs_while_a_transaction_is_interrupted"),
    ),
    Case(
        name="interrupted_blocks",
        guards="an interrupted transaction must block further mutation",
        edits=(Edit("ainative/lifecycle/installer.py",
                    "    pending = txnlib.interrupted(project)\n    if pending:\n",
                    "    pending = txnlib.interrupted(project)\n    if False:\n"),),
        test=("tests.test_lifecycle_transactions.TransactionSafety"
              ".test_an_interrupted_journal_is_detected_and_blocks_further_mutation"),
    ),
    Case(
        name="profile_preservation",
        guards="a downgrade must preserve the Verified history",
        # Also two layers: the data-root short-circuit in build_install_plan,
        # and the PRESERVE decision inside plan_component_removal.
        edits=(Edit("ainative/lifecycle/planner.py",
                    "        if component.ownership == manifestlib.USER_DATA:\n",
                    "        if False:\n"),
               Edit("ainative/lifecycle/planner.py",
                    "        return Change(REMOVE if purge else PRESERVE, entry.path, "
                    "entry.component,\n",
                    "        return Change(REMOVE, entry.path, entry.component,\n")),
        test=("tests.test_lifecycle_matrix.TransitionMatrix"
              ".test_verified_switch_standard_preserves_the_audit_trail"),
    ),
    Case(
        name="purge_confirmation",
        guards="--purge must refuse without confirmation when there is no terminal",
        edits=(Edit("ainative/lifecycle/uninstaller.py",
                    "    if purge and not assume_yes and not interactive:\n",
                    "    if False:\n"),),
        test=("tests.test_lifecycle_matrix.TransitionMatrix"
              ".test_purge_refuses_without_confirmation_when_there_is_no_terminal"),
    ),
    Case(
        name="layer_boundary",
        guards="installing Standard must not load a Work Plane authority module",
        edits=(Edit("ainative/lifecycle/installer.py",
                    'TRUST_ANCHOR_RELATIVE = ".ai-native/trust/project_trust.json"\n',
                    "from ainative_workplane.bootstrap import TRUST_RELATIVE\n"
                    "TRUST_ANCHOR_RELATIVE = TRUST_RELATIVE.as_posix()\n"),),
        test=("tests.test_lifecycle_cli.LayerBoundary"
              ".test_the_lifecycle_layer_never_imports_the_work_plane"),
    ),
    Case(
        name="external_block_scope",
        guards="uninstall must take back only the managed region of a config file",
        edits=(Edit("ainative/lifecycle/external.py",
                    "    remaining = before + after\n    if not remaining.strip():\n"
                    "        return None, True\n    return remaining, True\n",
                    "    return None, True\n"),),
        test=("tests.test_lifecycle_ownership.ExternalConfiguration"
              ".test_user_lines_added_after_the_block_survive_uninstall"),
    ),
)


def _scratch_repo(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name in COPIED:
        source = REPO / name
        if source.is_dir():
            shutil.copytree(source, destination / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                          ".pytest_cache"))
    for name in COPIED_FILES:
        if (REPO / name).is_file():
            shutil.copy2(REPO / name, destination / name)
    return destination


def _run_test(root: Path, target: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONPATH": str(root), "PYTHONIOENCODING": "utf-8"}
    for name in ("AINATIVE_UPDATE_PROVIDER", "AINATIVE_UPDATE_LOCAL_DIR",
                 "AINATIVE_STACK_SOURCE", "AINATIVE_NO_UPDATE_CHECK"):
        environment.pop(name, None)
    return subprocess.run([sys.executable, "-m", "unittest", target, "-q"],
                          cwd=str(root), capture_output=True, text=True,
                          env=environment, timeout=TEST_TIMEOUT_SECONDS)


def check(case: Case, workspace: Path) -> dict:
    """Remove one guard, run its test, and require that the test fails."""

    root = _scratch_repo(workspace / case.name)
    for edit in case.edits:
        text = (root / edit.file).read_text(encoding="utf-8")
        if edit.find not in text:
            return {"case": case.name, "guards": case.guards, "status": "STALE",
                    "detail": f"the guarded text is no longer present in {edit.file}; "
                              "this case must be updated or removed"}

    baseline = _run_test(root, case.test)
    if baseline.returncode != 0:
        return {"case": case.name, "guards": case.guards, "status": "BASELINE_RED",
                "detail": (baseline.stdout + baseline.stderr)[-400:]}

    for edit in case.edits:
        target = root / edit.file
        text = target.read_text(encoding="utf-8")
        target.write_text(text.replace(edit.find, edit.replace, 1), encoding="utf-8")

    without = _run_test(root, case.test)
    if without.returncode == 0:
        return {"case": case.name, "guards": case.guards, "status": "VACUOUS",
                "detail": "the test still passes with the guard removed - "
                          "it proves nothing"}
    return {"case": case.name, "guards": case.guards, "status": "NON_VACUOUS",
            "test": case.test}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", default=[],
                        help="run only these cases (repeatable)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    selected = [case for case in CASES if not args.case or case.name in args.case]
    if not selected:
        print(f"no such case; known: {', '.join(c.name for c in CASES)}", file=sys.stderr)
        return 2

    results = []
    with tempfile.TemporaryDirectory(prefix="ainative-nonvacuity-") as scratch:
        workspace = Path(scratch)
        for case in selected:
            outcome = check(case, workspace)
            results.append(outcome)
            if not args.json:
                mark = "OK  " if outcome["status"] == "NON_VACUOUS" else "FAIL"
                print(f"[{mark}] {outcome['case']:<24} {outcome['guards']}")
                if outcome["status"] != "NON_VACUOUS":
                    print(f"        {outcome['status']}: {outcome.get('detail', '')}")

    failures = [item for item in results if item["status"] != "NON_VACUOUS"]
    if args.json:
        # `observations` is what a substance adapter reads: how many guards were
        # actually proved, not how many were attempted. A run that proves fewer
        # than the caller declared is suspicious rather than a silent pass.
        print(json.dumps({"observations": len(results) - len(failures),
                          "attempted": len(results),
                          "cases": results, "passed": not failures},
                         indent=2, sort_keys=True))
    else:
        print(f"\n{len(results) - len(failures)}/{len(results)} guards proved non-vacuous.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
