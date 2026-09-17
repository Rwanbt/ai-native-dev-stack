"""The release gates: the dist chain, the PyPI half, the published-asset check.

Three separate statements a release must be able to make, each with its own
failure mode a stranger would only discover after publishing:

* every built artifact carries the release version (PyPI runs the wheel/sdist
  half without the lifecycle bundle);
* the release GitHub is about to make visible carries exactly the built assets,
  at the same sizes and digests;
* the gate itself fails when a label drifts - a gate that cannot fail is a
  comment.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for extra in (REPO / "scripts", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import check_release_versions as gate  # noqa: E402
import check_published_assets as published  # noqa: E402
import check_bridge_release as bridge  # noqa: E402
import check_release_gate as release_gate  # noqa: E402
from ainative.lifecycle import provider as providerlib  # noqa: E402
from ainative.lifecycle.errors import LifecycleError  # noqa: E402


def make_wheel(dist: Path, version: str) -> Path:
    path = dist / f"ainative_dev_stack-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"ainative_dev_stack-{version}.dist-info/METADATA",
                         f"Metadata-Version: 2.1\nName: ainative-dev-stack\nVersion: {version}\n")
    return path


def make_sdist(dist: Path, version: str) -> Path:
    path = dist / f"ainative_dev_stack-{version}.tar.gz"
    payload = f"Metadata-Version: 2.1\nName: ainative-dev-stack\nVersion: {version}\n".encode()
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(f"ainative_dev_stack-{version}/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return path


class DistChain(unittest.TestCase):

    def test_the_pypi_half_passes_without_a_bundle(self):
        with tempfile.TemporaryDirectory(prefix="pypi-gate-") as staging:
            dist = Path(staging)
            make_wheel(dist, "2.3.0")
            make_sdist(dist, "2.3.0")
            checked = gate.check_dist("2.3.0", dist, require_bundle=False)
        self.assertIn("ainative_dev_stack-2.3.0-py3-none-any.whl", checked)
        self.assertIn("ainative_dev_stack-2.3.0.tar.gz", checked)

    def test_the_default_requires_the_bundle(self):
        with tempfile.TemporaryDirectory(prefix="pypi-gate-") as staging:
            dist = Path(staging)
            make_wheel(dist, "2.3.0")
            make_sdist(dist, "2.3.0")
            with self.assertRaises(gate.ReleaseVersionMismatch):
                gate.check_dist("2.3.0", dist)

    def test_a_stale_artifact_of_another_version_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="pypi-gate-") as staging:
            dist = Path(staging)
            make_wheel(dist, "2.3.0")
            make_sdist(dist, "2.3.0")
            make_wheel(dist, "2.2.2")
            with self.assertRaises(gate.ReleaseVersionMismatch) as raised:
                gate.check_dist("2.3.0", dist, require_bundle=False)
            self.assertIn("another version", str(raised.exception))


class PublishedAssets(unittest.TestCase):

    def dist(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory(prefix="assets-gate-")
        root = Path(directory.name)
        make_wheel(root, "2.3.0")
        make_sdist(root, "2.3.0")
        return directory, root

    def published(self, dist: Path, **overrides) -> list[dict]:
        import hashlib

        assets = []
        for path in sorted(dist.iterdir()):
            payload = path.read_bytes()
            asset = {"name": path.name, "size": len(payload),
                     "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
            asset.update(overrides.get(path.name, {}))
            assets.append(asset)
        return assets

    def test_a_matching_published_set_passes(self):
        directory, dist = self.dist()
        self.addCleanup(directory.cleanup)
        checked = published.compare(dist, self.published(dist))
        self.assertEqual(len(checked), 2)

    def test_a_missing_asset_is_refused(self):
        directory, dist = self.dist()
        self.addCleanup(directory.cleanup)
        assets = self.published(dist)[1:]
        with self.assertRaises(published.PublishedAssetMismatch):
            published.compare(dist, assets)

    def test_a_report_file_inside_dist_is_not_counted_as_an_asset(self):
        directory, dist = self.dist()
        self.addCleanup(directory.cleanup)
        board = self.published(dist)          # computed before the report exists
        report = dist / "assets.json"
        report.write_text("{}", encoding="utf-8")
        # Without the exclusion this raised "assets on the release that were
        # not built: ['assets.json']" - the v2.3.0 release abort.
        checked = published.compare(dist, board, assets_json=report)
        self.assertEqual(len(checked), 2)
        self.assertNotIn("assets.json", checked)

    def test_a_size_or_digest_mismatch_is_refused(self):
        directory, dist = self.dist()
        self.addCleanup(directory.cleanup)
        wheel = next(dist.glob("*.whl"))
        with self.assertRaises(published.PublishedAssetMismatch):
            published.compare(dist, self.published(dist, **{wheel.name: {"size": 1}}))
        with self.assertRaises(published.PublishedAssetMismatch):
            published.compare(dist, self.published(
                dist, **{wheel.name: {"digest": "sha256:" + "0" * 64}}))


class GateNonVacuity(unittest.TestCase):
    """A drifting tag must fail the gate; otherwise it guards nothing."""

    def test_a_tag_that_does_not_name_the_version_fails(self):
        with self.assertRaises(gate.ReleaseVersionMismatch):
            gate.check_labels(REPO, "v999.0.0")


class BridgeReleaseGate(unittest.TestCase):
    """A V3 publication is blocked until a V2-consumable bridge exists (#157)."""

    class FakeProvider:
        def __init__(self, outcome: object) -> None:
            self.outcome = outcome

        def latest(self, channel: str):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    def release(self, version: str = "2.5.0", digest: str | None = "a" * 64):
        return providerlib.Release(version=version, url="https://example.invalid/b.zip",
                                   digest=digest)

    def test_a_verifiable_bridge_release_passes(self):
        record = bridge.verify_bridge_release("2.5.0", provider=self.FakeProvider(self.release()))
        self.assertEqual(record["bridge_version"], "2.5.0")
        self.assertEqual(record["lifecycle_bundle"], "ainative-lifecycle-v2-2.5.0.zip")
        self.assertEqual(record["sha256"], "a" * 64)

    def test_a_missing_or_unpublished_bridge_release_blocks(self):
        provider = self.FakeProvider(LifecycleError("UPDATE_CHECK_FAILED", "HTTP 404"))
        with self.assertRaises(bridge.BridgeReleaseUnverified) as raised:
            bridge.verify_bridge_release("2.5.0", provider=provider)
        self.assertIn("UPDATE_CHECK_FAILED", str(raised.exception))

    def test_a_bridge_without_a_lifecycle_bundle_blocks(self):
        provider = self.FakeProvider(
            LifecycleError("UPDATE_INTEGRITY_METADATA_MISSING", "no bundle"))
        with self.assertRaises(bridge.BridgeReleaseUnverified) as raised:
            bridge.verify_bridge_release("2.5.0", provider=provider)
        self.assertIn("UPDATE_INTEGRITY_METADATA_MISSING", str(raised.exception))

    def test_a_future_protocol_release_is_not_a_bridge(self):
        provider = self.FakeProvider(
            LifecycleError("CLI_UPDATE_REQUIRED", "publishes lifecycle protocol 3"))
        with self.assertRaises(bridge.BridgeReleaseUnverified) as raised:
            bridge.verify_bridge_release("2.5.0", provider=provider)
        self.assertIn("CLI_UPDATE_REQUIRED", str(raised.exception))

    def test_a_release_declaring_another_version_blocks(self):
        provider = self.FakeProvider(self.release(version="2.4.9"))
        with self.assertRaises(bridge.BridgeReleaseUnverified) as raised:
            bridge.verify_bridge_release("2.5.0", provider=provider)
        self.assertIn("declares version", str(raised.exception))

    def test_a_bridge_without_a_published_digest_blocks(self):
        provider = self.FakeProvider(self.release(digest=None))
        with self.assertRaises(bridge.BridgeReleaseUnverified):
            bridge.verify_bridge_release("2.5.0", provider=provider)

    def test_a_non_semver_bridge_version_blocks(self):
        with self.assertRaises(bridge.BridgeReleaseUnverified):
            bridge.verify_bridge_release("latest", provider=self.FakeProvider(self.release()))

    def test_a_missing_bridge_version_is_a_configuration_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = bridge.main(["--bridge-version", ""])
        self.assertEqual(code, 2)
        self.assertIn("BLOCK RELEASE", stderr.getvalue())

    def test_the_gate_resolves_through_the_v2_selection_path(self):
        """Not a mock of the gate: the real provider, the real selection rules."""

        document = json.dumps({"tag_name": "v2.5.0", "assets": [
            {"name": "ainative-lifecycle-v2-2.5.0.zip",
             "browser_download_url": "https://example.invalid/b.zip",
             "digest": "sha256:" + "b" * 64}]}).encode("utf-8")
        provider = providerlib.ReleaseApiProvider(
            "https://example.invalid/releases/tags/v2.5.0")
        provider._get = lambda url, limit: document
        record = bridge.verify_bridge_release("2.5.0", provider=provider)
        self.assertEqual(record["sha256"], "b" * 64)


class BridgeGatePolicy(unittest.TestCase):
    """The publication protocol comes from the artifacts, never a variable (#177).

    Non-vacuity: each of the five outcomes is pinned, and the workflow-level
    simulation runs through `main()` — the same entry point the release
    workflow invokes.
    """

    def dist(self, *names: str) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="release-gate-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name in names:
            (root / name).write_bytes(b"x")
        return root

    def unresolved(self, version: str) -> dict:
        raise bridge.BridgeReleaseUnverified(
            f"a V2 runtime cannot resolve the bridge release {version}: "
            "UPDATE_INTEGRITY_METADATA_MISSING: no bundle")

    def resolvable(self, version: str) -> dict:
        return {"bridge_version": version, "lifecycle_bundle": f"v2-{version}",
                "sha256": "a" * 64, "source": "https://example.invalid"}

    def test_v2_publication_without_the_variable_is_allowed(self):
        outcome = release_gate.evaluate(
            self.dist("ainative-lifecycle-v2-2.4.4.zip"), "")
        self.assertEqual(outcome["decision"], "ALLOW")
        self.assertEqual(outcome["protocol"], 2)
        self.assertEqual(outcome["bridge"], "not-applicable")

    def test_v3_publication_without_the_variable_blocks(self):
        for artifacts in (("ainative-release-v3.json",),
                          ("ainative-lifecycle-v3-2.5.0.zip",)):
            with self.subTest(artifacts=artifacts):
                outcome = release_gate.evaluate(self.dist(*artifacts), "")
                self.assertEqual(outcome["decision"], "BLOCK")
                self.assertEqual(outcome["protocol"], 3)
                self.assertIn("V3_BRIDGE_RELEASE", outcome["detail"])

    def test_the_workflow_entry_point_blocks_a_v3_publication_without_the_variable(self):
        dist = self.dist("ainative-release-v3.json", "ainative-lifecycle-v3-2.5.0.zip")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = release_gate.main(["--dist", str(dist), "--bridge-version", ""])
        self.assertEqual(code, 1)
        self.assertIn("BLOCK RELEASE", stderr.getvalue())

    def test_v3_publication_with_a_nonexistent_bridge_blocks(self):
        outcome = release_gate.evaluate(self.dist("ainative-release-v3.json"), "9.9.9",
                                        verify=self.unresolved)
        self.assertEqual(outcome["decision"], "BLOCK")
        self.assertEqual(outcome["bridge"], "unverified")
        self.assertIn("cannot resolve", outcome["detail"])

    def test_v3_publication_with_a_bundle_less_bridge_blocks(self):
        outcome = release_gate.evaluate(self.dist("ainative-release-v3.json"), "2.4.4",
                                        verify=self.unresolved)
        self.assertEqual(outcome["decision"], "BLOCK")

    def test_v3_publication_with_a_verifiable_bridge_passes(self):
        outcome = release_gate.evaluate(self.dist("ainative-release-v3.json"), "2.4.4",
                                        verify=self.resolvable)
        self.assertEqual(outcome["decision"], "ALLOW")
        self.assertEqual(outcome["bridge"], "verified")
        self.assertEqual(outcome["record"]["bridge_version"], "2.4.4")

    def test_a_missing_dist_directory_is_a_configuration_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = release_gate.main(["--dist", str(Path("nope") / "absent")])
        self.assertEqual(code, 2)
        self.assertIn("configuration error", stderr.getvalue())


def make_v3_bundle(dist: Path, version: str, *, protocol: int = 3,
                   payload_version: str | None = None) -> Path:
    path = dist / f"ainative-lifecycle-v3-{version}.zip"
    document = {"schema_name": "lifecycle_protocol", "protocol_version": protocol,
                "release_version": version, "payload_root": "stack"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("lifecycle-protocol.json", json.dumps(document))
        archive.writestr("stack/VERSION", f"{payload_version or version}\n")
    return path


def make_v3_manifest(dist: Path, version: str, *, manifest_version: str | None = None,
                     runtime: str | None = None, artifact_name: str | None = None,
                     artifact_version: str | None = None, artifact_sha: str | None = None,
                     artifact_size: int | None = None) -> Path:
    import hashlib

    bundle = dist / f"ainative-lifecycle-v3-{version}.zip"
    payload = bundle.read_bytes()
    document = {
        "schema": "ainative.release", "protocol": "v3",
        "version": manifest_version or version, "channel": "stable",
        "compatibility": {"runtime_version": runtime or version},
        "artifacts": [{
            "name": artifact_name or f"ainative-lifecycle-v3-{version}.zip",
            "kind": "lifecycle", "version": artifact_version or version,
            "sha256": artifact_sha or hashlib.sha256(payload).hexdigest(),
            "size": artifact_size if artifact_size is not None else len(payload)}],
        "provenance": {"source": "test"},
    }
    path = dist / "ainative-release-v3.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class V3DistChain(unittest.TestCase):
    """A V3 dist is validated through the manifest, the anchor and the chain."""

    VERSION = "2.5.0"

    def dist(self) -> Path:
        directory = tempfile.TemporaryDirectory(prefix="v3-dist-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        make_wheel(root, self.VERSION)
        make_sdist(root, self.VERSION)
        make_v3_bundle(root, self.VERSION)
        make_v3_manifest(root, self.VERSION)
        return root

    def test_a_v3_dist_passes(self):
        checked = gate.check_dist(self.VERSION, self.dist())
        self.assertIn(f"ainative-lifecycle-v3-{self.VERSION}.zip", checked)
        self.assertIn("ainative-release-v3.json", checked)

    def test_the_wrong_protocol_inside_the_bundle_is_refused(self):
        root = self.dist()
        (root / f"ainative-lifecycle-v3-{self.VERSION}.zip").unlink()
        make_v3_bundle(root, self.VERSION, protocol=2)
        make_v3_manifest(root, self.VERSION)
        with self.assertRaises(gate.ReleaseVersionMismatch) as raised:
            gate.check_dist(self.VERSION, root)
        self.assertIn("declares protocol 2", str(raised.exception))

    def test_a_manifest_naming_another_version_is_refused(self):
        root = self.dist()
        make_v3_manifest(root, self.VERSION, manifest_version="2.5.1")
        with self.assertRaises(gate.ReleaseVersionMismatch):
            gate.check_dist(self.VERSION, root)

    def test_a_runtime_mismatch_is_refused(self):
        root = self.dist()
        make_v3_manifest(root, self.VERSION, runtime="2.4.9")
        with self.assertRaises(gate.ReleaseVersionMismatch):
            gate.check_dist(self.VERSION, root)

    def test_a_tampered_bundle_is_refused_by_the_anchor(self):
        root = self.dist()
        make_v3_manifest(root, self.VERSION, artifact_sha="0" * 64)
        with self.assertRaises(gate.ReleaseVersionMismatch) as raised:
            gate.check_dist(self.VERSION, root)
        self.assertIn("does not match the manifest", str(raised.exception))

    def test_a_wrong_artifact_filename_is_refused(self):
        root = self.dist()
        make_v3_manifest(root, self.VERSION, artifact_name="other.zip")
        with self.assertRaises(gate.ReleaseVersionMismatch):
            gate.check_dist(self.VERSION, root)

    def test_the_bundle_internal_version_must_agree(self):
        root = self.dist()
        (root / f"ainative-lifecycle-v3-{self.VERSION}.zip").unlink()
        make_v3_bundle(root, self.VERSION, payload_version="2.4.9")
        make_v3_manifest(root, self.VERSION)
        with self.assertRaises(gate.ReleaseVersionMismatch):
            gate.check_dist(self.VERSION, root)

    def test_a_mixed_v2_v3_dist_is_refused(self):
        root = self.dist()
        (root / f"ainative-lifecycle-v2-{self.VERSION}.zip").write_bytes(b"x")
        with self.assertRaises(gate.ReleaseVersionMismatch) as raised:
            gate.check_dist(self.VERSION, root)
        self.assertIn("mixes", str(raised.exception))

    def test_forcing_protocol_2_on_a_v3_dist_is_refused(self):
        with self.assertRaises(gate.ReleaseVersionMismatch) as raised:
            gate.check_dist(self.VERSION, self.dist(), protocol=2)
        self.assertIn("protocol 3", str(raised.exception))


if __name__ == "__main__":
    unittest.main()