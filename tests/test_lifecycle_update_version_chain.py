"""The release version chain: tag == VERSION == package == bundle == runtime.

Two refusals that v2.2.1 did not implement are pinned here:

* A release may not publish a lifecycle bundle named for another version, and
  an old lifecycle runtime may not apply a target it does not know. The exact
  transition with real wheels lives in `scripts/lifecycle_upgrade_e2e.py`;
  these are the mutation-level proofs (AUD-201 / AUD-202).

* A cached availability notice may not outrank the state it describes: after
  an update lands, `update check` must stop announcing the version the project
  just moved to (#131).
"""

from __future__ import annotations

import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.lifecycle_support import (LifecycleTestCase, build_distribution_tree,
                                     make_release_archive, write_text)
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import state as statelib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle.digest import digest_file
from ainative.lifecycle.errors import LifecycleError

TARGET = "2.2.2"


def project_snapshot(project: Path) -> dict:
    """Every file under the project, by relative path and digest."""

    return {path.relative_to(project).as_posix(): digest_file(path) or ""
            for path in project.rglob("*") if path.is_file()}


# --- F/G: the reusable release gate -----------------------------------------


class ReleaseVersionGate(unittest.TestCase):
    """`scripts/check_release_versions.py` refuses every split label."""

    @classmethod
    def setUpClass(cls) -> None:
        scripts = REPO / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import check_release_versions

        cls.gate = check_release_versions

    def test_the_checkout_labels_agree_and_its_tag_names_the_version(self):
        version = self.gate.check_labels(REPO)
        self.assertEqual(self.gate.check_labels(REPO, f"v{version}"), version)

    def test_a_tag_that_does_not_name_the_version_is_refused(self):
        version = self.gate.check_labels(REPO)
        with self.assertRaises(self.gate.ReleaseVersionMismatch) as raised:
            self.gate.check_labels(REPO, "v999.0.0")
        self.assertIn(version, str(raised.exception))

    def test_two_disagreeing_package_labels_refuse_the_gate(self):
        """G: VERSION != ainative.__version__ still fails the build gate."""

        from _payload_staging import VersionMismatch

        with tempfile.TemporaryDirectory(prefix="ainative-gate-") as staging:
            root = Path(staging)
            (root / "ainative").mkdir()
            write_text(root / "VERSION", "1.0.0\n")
            write_text(root / "ainative" / "__init__.py", '__version__ = "2.0.0"\n')
            write_text(root / "AGENTS.md", "<!-- stack-version: 1.0.0 -->\n")
            with self.assertRaises(VersionMismatch):
                self.gate.check_labels(root)

    def test_an_agents_header_that_disagrees_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="ainative-gate-") as staging:
            root = Path(staging)
            (root / "ainative").mkdir()
            write_text(root / "VERSION", "1.0.0\n")
            write_text(root / "ainative" / "__init__.py", '__version__ = "1.0.0"\n')
            write_text(root / "AGENTS.md", "<!-- stack-version: 0.9.0 -->\n")
            with self.assertRaises(self.gate.ReleaseVersionMismatch):
                self.gate.check_labels(root)


def make_wheel(dist: Path, declared: str, filename_version: str | None = None) -> Path:
    path = dist / f"ainative_dev_stack-{filename_version or declared}-py3-none-any.whl"
    metadata = (f"Metadata-Version: 2.1\nName: ainative-dev-stack\n"
                f"Version: {declared}\n")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"ainative_dev_stack-{declared}.dist-info/METADATA", metadata)
    return path


def make_sdist(dist: Path, declared: str, filename_version: str | None = None) -> Path:
    path = dist / f"ainative_dev_stack-{filename_version or declared}.tar.gz"
    payload = (f"Metadata-Version: 2.1\nName: ainative-dev-stack\n"
               f"Version: {declared}\n").encode("utf-8")
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(f"ainative_dev_stack-{declared}/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return path


def make_bundle(dist: Path, filename_version: str, internal_version: str) -> Path:
    path = dist / f"ainative-dev-stack-{filename_version}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("VERSION", f"{internal_version}\n")
    return path


class ReleaseDistGate(unittest.TestCase):
    """`--dist`: filenames, wheel METADATA, sdist PKG-INFO, bundle VERSION."""

    def gate_check(self, dist: Path):
        scripts = REPO / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import check_release_versions

        return check_release_versions.check_dist(TARGET, dist)

    def test_a_consistent_dist_tree_passes_and_all_artifacts_are_named(self):
        with tempfile.TemporaryDirectory(prefix="ainative-dist-") as staging:
            dist = Path(staging)
            make_bundle(dist, TARGET, TARGET)
            make_wheel(dist, TARGET)
            make_sdist(dist, TARGET)
            checked = self.gate_check(dist)
            self.assertIn(f"ainative-dev-stack-{TARGET}.zip", checked)
            self.assertIn(f"ainative_dev_stack-{TARGET}-py3-none-any.whl", checked)
            self.assertIn(f"ainative_dev_stack-{TARGET}.tar.gz", checked)

    def test_a_bundle_whose_internal_version_differs_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="ainative-dist-") as staging:
            dist = Path(staging)
            make_bundle(dist, TARGET, "2.2.1")
            make_wheel(dist, TARGET)
            make_sdist(dist, TARGET)
            with self.assertRaises(Exception) as raised:
                self.gate_check(dist)
            self.assertIn("VERSION", str(raised.exception))

    def test_a_wheel_wearing_the_wrong_version_metadata_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="ainative-dist-") as staging:
            dist = Path(staging)
            make_bundle(dist, TARGET, TARGET)
            make_wheel(dist, "2.2.1", filename_version=TARGET)
            make_sdist(dist, TARGET)
            with self.assertRaises(Exception) as raised:
                self.gate_check(dist)
            self.assertIn("metadata version", str(raised.exception))

    def test_an_artifact_of_another_version_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="ainative-dist-") as staging:
            dist = Path(staging)
            make_bundle(dist, TARGET, TARGET)
            make_wheel(dist, TARGET)
            make_sdist(dist, TARGET)
            make_bundle(dist, "2.2.1", "2.2.1")
            with self.assertRaises(Exception) as raised:
                self.gate_check(dist)
            self.assertIn("another version", str(raised.exception))


# --- A: the official asset must be named for the release --------------------


class OfficialAssetSelection(unittest.TestCase):

    def provider(self, tag: str, asset_name: str):
        document = json.dumps({
            "tag_name": tag,
            "assets": [{"name": asset_name,
                        "browser_download_url": f"https://example.invalid/{asset_name}",
                        "digest": "sha256:" + "0" * 64}],
        }).encode("utf-8")
        provider = providerlib.ReleaseApiProvider("https://example.invalid/releases/latest")
        provider._get = lambda url, limit: document
        return provider

    def test_a_release_publishing_another_version_bundle_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            self.provider("v2.2.2", "ainative-dev-stack-2.2.1.zip").latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_VERSION_MISMATCH")
        self.assertEqual(raised.exception.detail.get("published"),
                         "ainative-dev-stack-2.2.1.zip")
        self.assertEqual(raised.exception.detail.get("expected"),
                         "ainative-dev-stack-2.2.2.zip")

    def test_the_matching_bundle_is_selected(self):
        release = self.provider("v2.2.2", "ainative-dev-stack-2.2.2.zip").latest("stable")
        self.assertEqual(release.version, "2.2.2")
        self.assertEqual(release.digest, "0" * 64)

# --- B/C/D/E: the chain at the updater and local mirror ---------------------


class VersionChainFixture(LifecycleTestCase):
    """A v1 project, a local mirror publishing 2.2.2, a 2.2.2 runtime label."""

    def setUp(self) -> None:
        super().setUp()
        self.releases = self.root / "releases"
        self.releases.mkdir()
        self.target_tree = build_distribution_tree(self.root / "dist-target", TARGET)
        self.archive = make_release_archive(
            self.target_tree, self.releases / f"ainative-dev-stack-{TARGET}.zip")
        self.publish(TARGET, self.archive)
        self.set_env(providerlib.PROVIDER_ENV, "local")
        self.set_env(providerlib.LOCAL_SOURCE_ENV, str(self.releases))
        self.install("standard")
        self.assume_runtime(TARGET)

    def publish(self, version: str, archive: Path, digest: str | None = None) -> None:
        payload = {"channels": {"stable": {
            "version": version, "archive": archive.name,
            "sha256": digest if digest is not None
            else sha256(archive.read_bytes()).hexdigest(),
            "notes": f"release {version}"}}}
        (self.releases / "releases.json").write_text(json.dumps(payload), encoding="utf-8")


class VersionChainRefusals(VersionChainFixture):

    def test_a_local_index_whose_archive_names_another_version_is_refused(self):
        """C: {version: 2.2.2, archive: ainative-dev-stack-2.2.1.zip}."""

        other = make_release_archive(
            build_distribution_tree(self.root / "dist-other", "2.2.1"),
            self.releases / "ainative-dev-stack-2.2.1.zip")
        self.publish(TARGET, other)
        with self.assertRaises(LifecycleError) as raised:
            providerlib.build("stable").latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_VERSION_MISMATCH")

    def test_an_index_refusal_reaches_the_updater_without_any_write(self):
        other = make_release_archive(
            build_distribution_tree(self.root / "dist-other", "2.2.1"),
            self.releases / "ainative-dev-stack-2.2.1.zip")
        self.publish(TARGET, other)
        before = project_snapshot(self.project)
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "UPDATE_VERSION_MISMATCH")
        self.assertEqual(project_snapshot(self.project), before,
                         "a version-mismatched index touched the project")

    def test_a_bundle_whose_internal_version_differs_is_refused(self):
        """B + E: filename 2.2.2, contents 2.2.1 - refused, zero writes."""

        inner = build_distribution_tree(self.root / "dist-inner", "2.2.1")
        archive = make_release_archive(
            inner, self.releases / f"ainative-dev-stack-{TARGET}.zip")
        self.publish(TARGET, archive)
        before = project_snapshot(self.project)
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "UPDATE_VERSION_MISMATCH")
        self.assertEqual(raised.exception.detail.get("bundle_version"), "2.2.1")
        self.assertEqual(project_snapshot(self.project), before,
                         "a mismatched bundle touched the project")
        self.assertEqual(statelib.load(self.project).stack_version, "1.0.0")

    def test_a_consistent_release_applies_and_records_matching_versions(self):
        """D: release 2.2.2 + bundle 2.2.2 + internal 2.2.2 -> applied."""

        result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertTrue(result.applied)
        self.assertEqual(result.to_version, TARGET)
        state = statelib.load(self.project)
        self.assertEqual(state.stack_version, TARGET)
        self.assertEqual(state.source_version, TARGET)
        self.assertEqual(self.read("AGENTS.md"), f"# Engineering method {TARGET}\n")
        self.assertTrue(result.rollback_available)


class RuntimeFreshness(VersionChainFixture):

    def test_an_older_runtime_is_refused_before_any_write(self):
        before = project_snapshot(self.project)
        with mock.patch.object(updaterlib, "runtime_version", lambda: "2.2.1"):
            with self.assertRaises(LifecycleError) as raised:
                updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "CLI_UPDATE_REQUIRED")
        self.assertEqual(raised.exception.detail["runtime_version"], "2.2.1")
        self.assertEqual(raised.exception.detail["target_version"], TARGET)
        self.assertIn(f"@v{TARGET}", raised.exception.detail["upgrade_command"])
        self.assertEqual(project_snapshot(self.project), before,
                         "a refused update touched the project")
        self.assertEqual(statelib.load(self.project).stack_version, "1.0.0")
        self.assertFalse(updaterlib.cache_path(self.project).exists(),
                         "the refusal wrote a cache entry")

    def test_a_dry_run_with_an_older_runtime_raises_without_writing(self):
        before = project_snapshot(self.project)
        with mock.patch.object(updaterlib, "runtime_version", lambda: "2.2.1"):
            with self.assertRaises(LifecycleError) as raised:
                updaterlib.apply(self.project, dry_run=True, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "CLI_UPDATE_REQUIRED")
        self.assertEqual(project_snapshot(self.project), before)

    def test_detection_still_works_with_an_older_runtime(self):
        with mock.patch.object(updaterlib, "runtime_version", lambda: "2.2.1"):
            outcome = updaterlib.check(self.project, force=True)
        self.assertEqual(outcome.status, updaterlib.UPDATE_AVAILABLE)
        self.assertEqual(outcome.latest, TARGET)
        self.assertFalse(outcome.runtime_ready)
        self.assertEqual(outcome.runtime_version, "2.2.1")
        message = outcome.message()
        self.assertIn("Upgrade the CLI first", message)
        self.assertIn(f"@v{TARGET}", message)

    def test_a_status_notice_names_the_required_cli_upgrade(self):
        with mock.patch.object(updaterlib, "runtime_version", lambda: "2.2.1"):
            notice = updaterlib.cached_notice(self.project, allow_network=True)
        self.assertFalse(notice["runtime_ready"])
        self.assertIn("CLI upgrade required", updaterlib.notice_line(notice))

    def test_an_up_to_date_project_is_not_refused_by_a_newer_runtime(self):
        """Nothing to apply means nothing to gate: the truthful answer stands."""

        state = statelib.load(self.project)
        state.stack_version = TARGET
        statelib.save(self.project, state)
        with mock.patch.object(updaterlib, "runtime_version", lambda: "9.9.9"):
            result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertFalse(result.applied)
        self.assertEqual(result.check.status, updaterlib.UP_TO_DATE)

class StaleUpdateCache(VersionChainFixture):
    """#131: the cache may not announce an update the project already took."""

    def write_cache(self, payload: dict) -> None:
        statelib.write_atomic(updaterlib.cache_path(self.project),
                              json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def test_after_an_update_the_cached_availability_is_corrected(self):
        pre = updaterlib.check(self.project, force=True)
        self.assertEqual(pre.status, updaterlib.UPDATE_AVAILABLE)
        self.assertTrue(updaterlib.apply(self.project, distribution=self.distribution).applied)

        after = updaterlib.check(self.project)   # no --force: the cache answers
        self.assertTrue(after.from_cache)
        self.assertEqual(after.status, updaterlib.UP_TO_DATE)
        self.assertIn(f"Up to date ({TARGET})", after.message())

    def test_cached_notice_after_an_update_does_not_announce_the_applied_release(self):
        updaterlib.check(self.project, force=True)
        updaterlib.apply(self.project, distribution=self.distribution)
        state = statelib.load(self.project)
        notice = updaterlib.cached_notice(self.project, current=state.stack_version)
        self.assertEqual(notice["status"], updaterlib.UP_TO_DATE)
        self.assertNotIn("available", updaterlib.notice_line(notice))

    def test_a_cached_latest_older_than_the_project_is_up_to_date(self):
        updaterlib.apply(self.project, distribution=self.distribution)
        self.write_cache({"status": "UPDATE_AVAILABLE", "latest": "1.9.0",
                          "current": "1.9.0", "checked_at": statelib.now()})
        self.assertEqual(updaterlib.check(self.project).status, updaterlib.UP_TO_DATE)

    def test_a_malformed_cached_version_resolves_up_to_date_fail_safe(self):
        self.write_cache({"status": "UPDATE_AVAILABLE", "latest": "not-a-version",
                          "current": "1.0.0", "checked_at": statelib.now()})
        outcome = updaterlib.check(self.project)
        self.assertEqual(outcome.status, updaterlib.UP_TO_DATE)
        self.assertIn("no usable version", outcome.detail)

    def test_reading_the_cache_never_rewrites_it(self):
        updaterlib.check(self.project, force=True)   # a real pre-update cache
        updaterlib.apply(self.project, distribution=self.distribution)
        cache = updaterlib.cache_path(self.project)
        original = cache.read_bytes()
        self.assertEqual(updaterlib.check(self.project).status, updaterlib.UP_TO_DATE)
        self.assertEqual(cache.read_bytes(), original, "a read rewrote the cache")


class RollbackDryRunWording(VersionChainFixture):

    def test_the_cli_dry_run_says_would_roll_back_and_writes_nothing(self):
        updaterlib.apply(self.project, distribution=self.distribution)
        before = project_snapshot(self.project)
        completed = self.cli("update", "rollback", "--dry-run")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("dry-run", completed.stdout)
        self.assertIn("would roll back", completed.stdout)
        self.assertNotIn("rolled back to", completed.stdout)
        self.assertEqual(project_snapshot(self.project), before,
                         "a dry-run rollback wrote to the project")

    def test_the_json_dry_run_reports_dry_run_true(self):
        updaterlib.apply(self.project, distribution=self.distribution)
        completed = self.cli("update", "rollback", "--dry-run", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        record = json.loads(completed.stdout)
        self.assertTrue(record["dry_run"])
        self.assertEqual(record["operation"], "update rollback")

    def test_a_real_rollback_still_reports_the_restoration(self):
        updaterlib.apply(self.project, distribution=self.distribution)
        completed = self.cli("update", "rollback")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("rolled back to", completed.stdout)
        self.assertEqual(statelib.load(self.project).stack_version, "1.0.0")


if __name__ == "__main__":
    unittest.main()