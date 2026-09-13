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


if __name__ == "__main__":
    unittest.main()