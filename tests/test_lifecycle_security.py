"""Adversarial inputs: path traversal, links, tampered state, archive bombs.

Every input in these tests is data the lifecycle layer reads and then acts on —
a manifest, an install state, a release archive. Data that reaches `unlink()`
gets adversarial tests or it gets an incident.
"""

from __future__ import annotations

import json
import os
import shutil
import unittest
import zipfile
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, build_distribution_tree
from ainative.lifecycle import manifest as manifestlib
from ainative.lifecycle import paths as pathslib
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import recovery, state as statelib, updater as updaterlib
from ainative.lifecycle.errors import LifecycleError

TRAVERSAL_PATHS = (
    "../escaped.txt",
    "../../escaped.txt",
    "a/../../escaped.txt",
    "/etc/passwd",
    "C:/Windows/System32/x.dll",
    "C:\\Windows\\x.dll",
    "\\\\server\\share\\x",
    "//server/share/x",
    "a/./../../b",
    "",
    "   ",
)


class PathContainment(unittest.TestCase):

    def test_every_traversal_shape_is_refused(self):
        for candidate in TRAVERSAL_PATHS:
            with self.subTest(path=candidate):
                with self.assertRaises(LifecycleError) as raised:
                    pathslib.validate_relative(candidate)
                self.assertEqual(raised.exception.code, "PATH_ESCAPE")

    def test_a_nul_byte_is_refused(self):
        with self.assertRaises(LifecycleError):
            pathslib.validate_relative("a\x00b")

    def test_an_ordinary_relative_path_is_accepted(self):
        for candidate in ("a", "a/b", "a/b/c.txt", ".claude/skills/x/SKILL.md",
                          "with space/name.txt", "unicode/café/naïve.md"):
            with self.subTest(path=candidate):
                self.assertTrue(str(pathslib.validate_relative(candidate)))

    def test_case_folding_collision_is_detected(self):
        self.assertEqual(pathslib.collision_key("A/B.txt"), pathslib.collision_key("a/b.TXT"))


class LinkEscape(LifecycleTestCase):

    def _make_link(self, link: Path, target: Path) -> bool:
        """Create a directory link, or report that this machine will not allow it."""

        try:
            link.symlink_to(target, target_is_directory=True)
            return True
        except (OSError, NotImplementedError):
            if os.name != "nt":
                return False
            completed = shutil.which("cmd")
            if not completed:
                return False
            import subprocess

            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                    capture_output=True, text=True)
            return result.returncode == 0 and link.exists()

    def test_resolve_within_refuses_a_link_that_leaves_the_project(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "victim.txt").write_text("do not touch\n", encoding="utf-8")
        link = self.project / "escape"
        if not self._make_link(link, outside):
            self.skipTest("this machine does not allow creating directory links")

        with self.assertRaises(LifecycleError) as raised:
            pathslib.resolve_within(self.project, "escape/victim.txt")
        self.assertEqual(raised.exception.code, "PATH_ESCAPE")
        self.assertFalse(pathslib.is_within(self.project, link / "victim.txt"))
        self.assertTrue((outside / "victim.txt").is_file())

    def test_a_tampered_state_pointing_outside_cannot_delete_anything(self):
        outside = self.root / "outside"
        outside.mkdir()
        victim = outside / "victim.txt"
        victim.write_text("do not touch\n", encoding="utf-8")

        self.install("standard")
        state_file = self.project / statelib.STATE_RELATIVE
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["managed_files"].append({
            "path": "../outside/victim.txt", "component": "engineering-method",
            "ownership": "MANAGED_IMMUTABLE",
            "digest_at_install": "0" * 64, "created_by_ainative": True, "kind": "file"})
        state_file.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(LifecycleError) as raised:
            self.uninstall(purge=True, assume_yes=True)
        self.assertEqual(raised.exception.code, "PATH_ESCAPE")
        self.assertTrue(victim.is_file(), "a tampered state deleted a file outside the project")


class TamperedJournal(LifecycleTestCase):
    """A journal file lives in the project, so it is attacker-writable data."""

    def _plant(self, name: str, payload: dict) -> Path:
        from ainative.lifecycle import transaction as txnlib

        path = txnlib.transactions_dir(self.project) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_a_journal_id_that_escapes_cannot_make_repair_write_outside(self):
        from ainative.lifecycle import recovery

        self.install("standard")
        outside = self.root / "escaped.json"
        self._plant("evil.json", {
            "schema_version": 1, "id": "../../../../escaped", "operation": "update",
            "state": "APPLYING", "completed_changes": [],
            "backup_location": "../../../outside", "started_at": "2026-01-01"})

        recovery.repair(self.project, distribution=self.distribution, source=self.source)
        self.assertFalse(outside.exists(),
                         "a tampered journal id wrote outside the project root")

    def test_an_illegal_journal_is_ignored_rather_than_obeyed(self):
        from ainative.lifecycle import transaction as txnlib

        self.install("standard")
        self._plant("evil.json", {"schema_version": 1, "id": "../escape",
                                  "operation": "update", "state": "APPLYING",
                                  "started_at": "2026-01-01"})
        self.assertEqual(txnlib.interrupted(self.project), [],
                         "an illegal journal was treated as a real transaction")
        self.assertIn("evil.json", txnlib.malformed(self.project))

    def test_doctor_reports_an_illegal_journal_instead_of_hiding_it(self):
        from ainative.lifecycle import recovery

        self.install("standard")
        self._plant("evil.json", {"schema_version": 1, "id": "..", "operation": "update",
                                  "state": "APPLYING", "started_at": "2026-01-01"})
        diagnosis = recovery.diagnose(self.project, distribution=self.distribution)
        self.assertFalse(diagnosis.healthy)
        self.assertTrue(any(item["status"] == recovery.CORRUPTED
                            and "evil.json" in item["path"]
                            for item in diagnosis.findings), diagnosis.findings)

    def test_a_backup_location_that_escapes_is_refused_at_load(self):
        from ainative.lifecycle import transaction as txnlib
        from ainative.lifecycle.errors import LifecycleError

        with self.assertRaises(LifecycleError):
            txnlib.Journal.from_record({"id": "txn_ok", "operation": "update",
                                        "backup_location": "../../elsewhere"})

    def test_the_ids_this_code_writes_are_accepted(self):
        from ainative.lifecycle import state as statelib
        from ainative.lifecycle import transaction as txnlib

        identifier = statelib.new_identifier("txn")
        journal = txnlib.Journal.from_record({"id": identifier, "operation": "init",
                                              "backup_location":
                                              f".ai-native/lifecycle/backups/{identifier}"})
        self.assertEqual(journal.identifier, identifier)


class TamperedManifests(unittest.TestCase):

    def _write(self, directory: Path, components: dict, profiles: dict) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "components.json").write_text(
            json.dumps({"schema_version": 1, "components": components}), encoding="utf-8")
        (directory / "profiles.json").write_text(
            json.dumps({"schema_version": 1, "default": "standard", "profiles": profiles}),
            encoding="utf-8")
        return directory

    def setUp(self) -> None:
        import tempfile

        self.root = Path(tempfile.mkdtemp(prefix="ainative-manifest-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_a_manifest_destination_that_escapes_is_refused_at_load(self):
        directory = self._write(
            self.root / "a",
            {"evil": {"kind": "file", "ownership": "MANAGED_IMMUTABLE",
                      "source": "AGENTS.md", "destination": "../../etc/evil"}},
            {"standard": {"extends": None, "components": ["evil"]}})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "PATH_ESCAPE")

    def test_an_unknown_component_reference_is_refused(self):
        directory = self._write(
            self.root / "b",
            {"real": {"kind": "file", "ownership": "MANAGED_IMMUTABLE",
                      "source": "AGENTS.md", "destination": "AGENTS.md"}},
            {"standard": {"extends": None, "components": ["ghost"]}})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "COMPONENT_UNKNOWN")

    def test_an_inheritance_cycle_is_refused(self):
        directory = self._write(
            self.root / "c",
            {"real": {"kind": "file", "ownership": "MANAGED_IMMUTABLE",
                      "source": "AGENTS.md", "destination": "AGENTS.md"}},
            {"standard": {"extends": "verified", "components": ["real"]},
             "verified": {"extends": "standard", "components": []}})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "PROFILE_INVALID")

    def test_an_unknown_ownership_class_is_refused(self):
        directory = self._write(
            self.root / "d",
            {"real": {"kind": "file", "ownership": "ANYTHING_GOES",
                      "source": "AGENTS.md", "destination": "AGENTS.md"}},
            {"standard": {"extends": None, "components": ["real"]}})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")

    def test_two_tree_components_colliding_under_case_folding_are_refused(self):
        """Trees are the case the guard exists for, and were the case it skipped.

        Two directory components landing on the same path on a
        case-insensitive filesystem would interleave, each pruning the other's
        files (EMP-LC-015).
        """

        directory = self._write(
            self.root / "trees",
            {"one": {"kind": "tree", "ownership": "MANAGED_IMMUTABLE",
                     "source": "skills", "destination": "Skills"},
             "two": {"kind": "tree", "ownership": "MANAGED_IMMUTABLE",
                     "source": "skills", "destination": "skills"}},
            {"standard": {"extends": None, "components": ["one", "two"]}})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")

    def test_two_components_colliding_under_case_folding_are_refused(self):
        directory = self._write(
            self.root / "e",
            {"one": {"kind": "file", "ownership": "MANAGED_IMMUTABLE",
                     "source": "AGENTS.md", "destination": "Agents.md"},
             "two": {"kind": "file", "ownership": "MANAGED_IMMUTABLE",
                     "source": "AGENTS.md", "destination": "AGENTS.MD"}},
            {"standard": {"extends": None, "components": ["one", "two"]}})
        with self.assertRaises(LifecycleError) as raised:
            manifestlib.load(directory)
        self.assertEqual(raised.exception.code, "MANIFEST_INVALID")


class CorruptState(LifecycleTestCase):

    def test_unparseable_state_is_reported_not_ignored(self):
        self.install("standard")
        (self.project / statelib.STATE_RELATIVE).write_text("{not json", encoding="utf-8")
        with self.assertRaises(LifecycleError) as raised:
            statelib.load(self.project)
        self.assertEqual(raised.exception.code, "INSTALL_STATE_CORRUPTED")

    def test_doctor_survives_a_corrupt_state_and_says_so(self):
        self.install("standard")
        (self.project / statelib.STATE_RELATIVE).write_text("{not json", encoding="utf-8")
        diagnosis = recovery.diagnose(self.project, distribution=self.distribution)
        self.assertFalse(diagnosis.healthy)
        self.assertEqual(diagnosis.findings[0]["status"], recovery.CORRUPTED)

    def test_a_future_schema_version_is_refused_rather_than_guessed(self):
        self.install("standard")
        path = self.project / statelib.STATE_RELATIVE
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = statelib.SCHEMA_VERSION + 5
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(LifecycleError) as raised:
            statelib.load(self.project)
        self.assertEqual(raised.exception.code, "INSTALL_STATE_CORRUPTED")

    def test_a_tampered_digest_makes_the_file_user_modified_not_replaceable(self):
        self.install("standard")
        path = self.project / statelib.STATE_RELATIVE
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload["managed_files"]:
            if entry["path"] == "AGENTS.md":
                entry["digest_at_install"] = "f" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")

        original = self.read("AGENTS.md")
        self.uninstall()
        self.assertEqual(self.read("AGENTS.md"), original,
                         "a file whose recorded digest no longer matches was deleted")


class UpdateArchiveSafety(LifecycleTestCase):

    def _zip(self, entries: dict[str, str]) -> bytes:
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return buffer.getvalue()

    def test_an_archive_naming_a_traversal_path_is_refused_before_extraction(self):
        payload = self._zip({"stack/VERSION": "2.0.0\n", "../evil.txt": "pwned"})
        destination = self.root / "extract"
        with self.assertRaises(LifecycleError) as raised:
            updaterlib._safe_extract(payload, destination)
        self.assertEqual(raised.exception.code, "PATH_ESCAPE")
        self.assertFalse((self.root / "evil.txt").exists())

    def test_an_archive_naming_an_absolute_path_is_refused(self):
        payload = self._zip({"/etc/evil": "pwned"})
        with self.assertRaises(LifecycleError):
            updaterlib._safe_extract(payload, self.root / "extract2")

    def test_an_archive_with_too_many_entries_is_refused(self):
        entries = {f"stack/f{index}.txt": "x" for index in
                   range(updaterlib.MAX_ARCHIVE_ENTRIES + 1)}
        with self.assertRaises(LifecycleError) as raised:
            updaterlib._safe_extract(self._zip(entries), self.root / "extract3")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")

    def test_a_mismatched_digest_refuses_before_anything_is_written(self):
        with self.assertRaises(LifecycleError) as raised:
            providerlib.verify_archive(b"payload", "0" * 64)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")

    def test_a_matching_digest_is_accepted(self):
        from hashlib import sha256

        payload = b"payload"
        self.assertEqual(providerlib.verify_archive(payload, sha256(payload).hexdigest()),
                         sha256(payload).hexdigest())

    def test_a_non_https_release_source_is_refused(self):
        provider = providerlib.ReleaseApiProvider("http://example.invalid/releases")
        with self.assertRaises(LifecycleError) as raised:
            provider.latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")

    def test_an_archive_without_a_distribution_is_refused(self):
        payload = self._zip({"random/thing.txt": "x"})
        extracted = updaterlib._safe_extract(payload, self.root / "extract4")
        with self.assertRaises(LifecycleError) as raised:
            updaterlib._distribution_root(extracted)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")

    def test_a_well_formed_archive_extracts_into_a_distribution(self):
        build_distribution_tree(self.root / "release", "2.0.0")
        from tests.lifecycle_support import make_release_archive

        archive = make_release_archive(self.root / "release", self.root / "release.zip")
        extracted = updaterlib._safe_extract(archive.read_bytes(), self.root / "extract5")
        root = updaterlib._distribution_root(extracted)
        self.assertEqual((root / "VERSION").read_text(encoding="utf-8").strip(), "2.0.0")


if __name__ == "__main__":
    unittest.main()
