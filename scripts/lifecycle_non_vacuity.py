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
              ".test_a_failure_partway_through_leaves_the_old_profile_recorded"),
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
                    "            action = REMOVE if purge else PRESERVE\n",
                    "            action = REMOVE\n")),
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
