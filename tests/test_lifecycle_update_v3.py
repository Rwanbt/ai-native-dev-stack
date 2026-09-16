"""The V3 update path, end to end on a local mirror.

The updater prefers V3 when the source publishes an anchored manifest, and
falls back to the V2 path only when a complete enumeration proves the channel
is V2-era. Everything that can refuse happens before the first project write.
"""

from __future__ import annotations

import json
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, build_distribution_tree, write_text
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import release_v3 as release_v3lib
from ainative.lifecycle import state as statelib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle.errors import LifecycleError

TARGET = "2.0.0"


def make_v3_bundle(directory: Path, version: str, *, protocol: int = 3) -> Path:
    tree = build_distribution_tree(directory / f"dist-{version}", version)
    path = directory / release_v3lib.lifecycle_bundle_name(version)
    protocol_document = {"schema_name": "lifecycle_protocol",
                         "protocol_version": protocol, "release_version": version,
                         "payload_root": "stack"}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lifecycle-protocol.json", json.dumps(protocol_document))
        for item in sorted(tree.rglob("*")):
            if item.is_file():
                archive.write(item, f"stack/{item.relative_to(tree).as_posix()}")
    return path


class V3MirrorUpdate(LifecycleTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.releases = self.root / "releases"
        (self.releases / TARGET).mkdir(parents=True)
        self.bundle = make_v3_bundle(self.releases / TARGET, TARGET)
        self.manifest_document = {
            "schema": "ainative.release", "protocol": "v3", "version": TARGET,
            "channel": "stable",
            "compatibility": {"runtime_version": TARGET},
            "artifacts": [{"name": release_v3lib.lifecycle_bundle_name(TARGET),
                           "kind": "lifecycle", "version": TARGET,
                           "sha256": "", "size": 0}],
            "provenance": {"source": "test"},
        }
        self.record_bundle()
        self.publish()
        self.set_env(providerlib.PROVIDER_ENV, "local")
        self.set_env(providerlib.LOCAL_SOURCE_ENV, str(self.releases))
        self.install("standard")
        self.assume_runtime(TARGET)

    def record_bundle(self) -> None:
        payload = self.bundle.read_bytes()
        self.manifest_document["artifacts"][0]["sha256"] = sha256(payload).hexdigest()
        self.manifest_document["artifacts"][0]["size"] = len(payload)

    def publish(self, *, sha: str | None = None, size: int | None = None) -> None:
        manifest = json.dumps(self.manifest_document).encode("utf-8")
        write_text(self.releases / TARGET / "ainative-release-v3.json",
                   manifest.decode())
        index = {"channels": {"stable": {"version": TARGET, "manifest": {
            "file": "ainative-release-v3.json",
            "size": size if size is not None else len(manifest),
            "sha256": sha if sha is not None else sha256(manifest).hexdigest()}}}}
        write_text(self.releases / "releases.json", json.dumps(index))

    def snapshot(self) -> dict:
        from ainative.lifecycle.digest import digest_file

        return {path.relative_to(self.project).as_posix(): digest_file(path) or ""
                for path in self.project.rglob("*") if path.is_file()}

    def test_check_sees_the_v3_release(self):
        result = updaterlib.check(self.project, force=True, record=False)
        self.assertEqual(result.status, updaterlib.UPDATE_AVAILABLE)
        self.assertEqual(result.latest, TARGET)

    def test_a_v3_update_applies_end_to_end(self):
        result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertTrue(result.applied)
        self.assertEqual(result.to_version, TARGET)
        self.assertEqual(self.read("AGENTS.md"), f"# Engineering method {TARGET}\n")
        self.assertEqual(statelib.load(self.project).stack_version, TARGET)
        self.assertTrue(result.rollback_available)

    def test_a_tampered_v3_manifest_is_refused_before_any_write(self):
        self.publish(sha="a" * 64)
        before = self.snapshot()
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")
        self.assertEqual(self.snapshot(), before,
                         "a refused V3 update touched the project")

    def test_a_v3_bundle_carrying_the_v2_protocol_is_refused(self):
        self.bundle.unlink()
        self.bundle = make_v3_bundle(self.releases / TARGET, TARGET, protocol=2)
        self.record_bundle()
        self.publish()
        with self.assertRaises(LifecycleError) as raised:
            updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "UPDATE_VERSION_MISMATCH")

    def test_the_cli_reports_the_v3_check(self):
        record = json.loads(self.cli("update", "check", "--force", "--json").stdout)
        self.assertEqual(record["status"], updaterlib.UPDATE_AVAILABLE)
        self.assertEqual(record["latest"], TARGET)


if __name__ == "__main__":
    unittest.main()
