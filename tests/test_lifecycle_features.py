"""The feature model, State V2, and the one projection every reader shares.

ADR-0017 makes profiles (governance) and features (optional project-scope
capabilities) orthogonal. A V1 state predates `active_features`; it projects to
the declared legacy default — a GitHub project until it explicitly switches —
and migrates inside a normal mutation, state-last. These tests pin the model,
the projection and the migration, including every refusal that must never be a
silent pick: two work forges, an undeclared feature, a malformed catalogue.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, write_text
from ainative.lifecycle import features as featureslib
from ainative.lifecycle import manifest as manifestlib
from ainative.lifecycle import state as statelib
from ainative.lifecycle.errors import LifecycleError

LEGACY = "forge-github"
GITLAB = "forge-gitlab"


def write_catalogue(directory: Path, *, features: dict, legacy: str = "forge") -> Path:
    """A minimal catalogue: one component, one profile, the given features."""

    directory.mkdir(parents=True, exist_ok=True)
    write_text(directory / "components.json", json.dumps({
        "schema_version": 1,
        "components": {"tpl": {"kind": "file", "ownership": "MANAGED_MUTABLE",
                               "source": "AGENTS.md", "destination": "TEMPLATE.md"}}}))
    write_text(directory / "profiles.json", json.dumps({
        "schema_version": 1, "default": "standard",
        "profiles": {"standard": {"extends": None, "components": []}}}))
    write_text(directory / "features.json", json.dumps({
        "schema_version": 1, "legacy_default": legacy, "features": features}))
    return directory


class FeatureCatalogue(unittest.TestCase):

    def setUp(self) -> None:
        import shutil
        import tempfile

        self.root = Path(tempfile.mkdtemp(prefix="ainative-features-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.distribution = manifestlib.load()

    def feature(self, name: str, **fields) -> dict:
        base = {"scope": "project", "work_forge": False, "components": [], "conflicts": []}
        base.update(fields)
        return base

    def test_the_real_catalogue_declares_both_work_forges_and_a_default(self):
        github = self.distribution.feature(LEGACY)
        gitlab = self.distribution.feature(GITLAB)
        self.assertEqual(self.distribution.legacy_default_feature, LEGACY)
        for feature in (github, gitlab):
            self.assertEqual(feature.scope, manifestlib.FEATURE_SCOPE_PROJECT)
            self.assertTrue(feature.work_forge)
        self.assertIn(GITLAB, github.conflicts)
        self.assertIn(LEGACY, gitlab.conflicts)
        self.assertEqual(github.components, ("github-templates",))
        self.assertEqual(gitlab.components, ("gitlab-templates",))

    def test_an_undeclared_feature_id_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            self.distribution.feature("forge-sourceforge")
        self.assertEqual(raised.exception.code, "FEATURE_UNKNOWN")

    def test_a_machine_scope_entry_is_not_a_feature(self):
        directory = write_catalogue(
            self.root / "machine",
            features={"hal": self.feature("hal", scope="machine")})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")

    def test_asymmetric_conflicts_are_refused(self):
        directory = write_catalogue(
            self.root / "asymmetric",
            features={"a": self.feature("a", components=["tpl"], conflicts=["b"]),
                      "b": self.feature("b", components=[])})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")

    def test_a_component_claimed_by_two_features_is_refused(self):
        directory = write_catalogue(
            self.root / "claimed",
            features={"a": self.feature("a", components=["tpl"]),
                      "b": self.feature("b", components=["tpl"])})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")

    def test_a_feature_referencing_an_unknown_component_is_refused(self):
        directory = write_catalogue(
            self.root / "unknown-component",
            features={"a": self.feature("a", components=["ghost"])})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")

    def test_the_legacy_default_must_be_declared(self):
        directory = write_catalogue(
            self.root / "legacy", legacy="ghost",
            features={"a": self.feature("a")})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")


class StateProjection(LifecycleTestCase):
    """One projection, one answer — whatever schema is on disk."""

    def setUp(self) -> None:
        super().setUp()
        self.install("standard")

    def v1_record(self) -> dict:
        """Rewrite the state as the release before V2 wrote it."""

        path = statelib.state_path(self.project)
        record = json.loads(path.read_text(encoding="utf-8"))
        record["schema_version"] = 1
        record.pop("active_features", None)
        statelib.write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record

    def effective(self):
        return featureslib.project_install_state(
            statelib.load(self.project), manifestlib.load())

    def test_a_v1_project_projects_to_the_legacy_default(self):
        self.v1_record()
        effective = self.effective()
        self.assertEqual(effective.schema_version, 1)
        self.assertEqual(effective.active_features, (LEGACY,))
        self.assertTrue(effective.projected_from_legacy)
        self.assertTrue(effective.has_feature(LEGACY))

    def test_a_v1_verified_project_projects_to_the_legacy_default(self):
        self.switch("verified")
        self.v1_record()
        self.assertEqual(self.effective().active_features, (LEGACY,))

    def test_a_v1_project_with_a_gitlab_remote_still_projects_to_the_legacy_default(self):
        subprocess.run(["git", "-C", str(self.project), "remote", "add", "origin",
                        "https://gitlab.com/org/project.git"], check=True,
                       capture_output=True)
        self.v1_record()
        self.assertEqual(self.effective().active_features, (LEGACY,))

    def test_a_v1_project_with_no_remote_still_projects_to_the_legacy_default(self):
        remotes = subprocess.run(["git", "-C", str(self.project), "remote"],
                                 check=True, capture_output=True, text=True)
        self.assertEqual(remotes.stdout.strip(), "")
        self.v1_record()
        self.assertEqual(self.effective().active_features, (LEGACY,))

    def test_the_projection_is_read_only(self):
        from ainative.lifecycle.digest import digest_file

        self.v1_record()
        path = statelib.state_path(self.project)
        before = digest_file(path)
        self.effective()
        self.effective()
        self.assertEqual(digest_file(path), before)

    def test_a_v2_state_with_one_forge_projects_it(self):
        state = statelib.load(self.project)
        state.active_features = [GITLAB]
        statelib.save(self.project, state)
        self.assertEqual(self.effective().active_features, (GITLAB,))
        self.assertFalse(self.effective().projected_from_legacy)

    def test_a_v2_state_with_no_forge_is_valid(self):
        state = statelib.load(self.project)
        state.active_features = []
        statelib.save(self.project, state)
        self.assertEqual(self.effective().active_features, ())

    def test_a_v2_state_with_two_work_forges_is_refused(self):
        state = statelib.load(self.project)
        state.active_features = [LEGACY, GITLAB]
        statelib.save(self.project, state)
        from ainative.lifecycle.digest import digest_file

        before = digest_file(statelib.state_path(self.project))
        with self.assertRaises(LifecycleError) as raised:
            self.effective()
        self.assertEqual(raised.exception.code, "STATE_CONFLICTING_WORK_FORGE_FEATURES")
        self.assertEqual(digest_file(statelib.state_path(self.project)), before,
                         "a refused projection rewrote the state")

    def test_a_v2_state_naming_an_undeclared_feature_is_refused(self):
        state = statelib.load(self.project)
        state.active_features = ["forge-sourceforge"]
        statelib.save(self.project, state)
        with self.assertRaises(LifecycleError) as raised:
            self.effective()
        self.assertEqual(raised.exception.code, "INSTALL_STATE_CORRUPTED")

    def test_the_projection_is_idempotent(self):
        self.v1_record()
        first = self.effective()
        second = self.effective()
        self.assertEqual(first, second)
        state = statelib.load(self.project)
        statelib.save(self.project, state)
        self.assertEqual(self.effective(), second)


class StateMigration(LifecycleTestCase):

    def snapshot(self, *, skip_state: bool = True) -> dict:
        from ainative.lifecycle.digest import digest_file

        state_path = statelib.state_path(self.project)
        return {path.relative_to(self.project).as_posix(): digest_file(path) or ""
                for path in self.project.rglob("*")
                if path.is_file() and not (skip_state and path == state_path)}

    def v1_record(self) -> dict:
        path = statelib.state_path(self.project)
        record = json.loads(path.read_text(encoding="utf-8"))
        record["schema_version"] = 1
        record.pop("active_features", None)
        statelib.write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record

    def test_a_no_op_install_migrates_a_v1_state(self):
        self.install("standard")
        self.v1_record()
        before = self.snapshot()
        self.install("standard")
        state = statelib.load(self.project)
        self.assertEqual(state.schema_version, statelib.SCHEMA_VERSION)
        self.assertEqual(state.active_features, [LEGACY])
        self.assertEqual(self.snapshot(), before,
                         "the migration changed managed files")

    def test_migration_is_idempotent(self):
        from ainative.lifecycle.digest import digest_file

        self.install("standard")
        self.v1_record()
        self.install("standard")
        path = statelib.state_path(self.project)
        migrated = digest_file(path)
        self.install("standard")
        self.assertEqual(digest_file(path), migrated,
                         "a second install rewrote the migrated state")
        self.assertEqual(statelib.load(self.project).active_features, [LEGACY])

    def test_migrate_state_leaves_a_current_state_untouched(self):
        state = statelib.InstallState(active_features=[GITLAB])
        migrated = featureslib.migrate_state(state, manifestlib.load())
        self.assertIs(migrated, state)
        self.assertEqual(migrated.active_features, [GITLAB])

    def test_the_effective_feature_set_is_identical_across_the_migration(self):
        """Read-only parity: projection before == projection after (ADR-0017 §4)."""

        self.install("standard")
        self.v1_record()
        before = featureslib.project_install_state(statelib.load(self.project),
                                                   manifestlib.load())
        self.install("standard")
        after = featureslib.project_install_state(statelib.load(self.project),
                                                  manifestlib.load())
        self.assertEqual(before.active_features, after.active_features)
        self.assertEqual(before.active_profile, after.active_profile)


if __name__ == "__main__":
    unittest.main()
