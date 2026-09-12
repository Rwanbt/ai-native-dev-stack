"""The distribution's version labels: one fact, enforced everywhere.

v2.2.0 shipped `VERSION = 2.0.0` beside a 2.2.0 package, and the lifecycle
records the `VERSION` file, so a fresh install disagreed with the release it
came from (#125). These tests pin the invariant at every representation a user
or a build can observe: the checkout, the staged payload, the wheel payload,
and the packaged metadata.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import ainative                                                         # noqa: E402
from _payload_staging import (VersionMismatch, assert_version_consistency,  # noqa: E402
                              package_version, read_version, stage_payload)
from ainative.lifecycle import source as sourcelib                      # noqa: E402

from tests.lifecycle_support import write_text                          # noqa: E402


def _has_setuptools() -> bool:
    return subprocess.run([sys.executable, "-c", "import setuptools"],
                          capture_output=True).returncode == 0


class FreshCheckoutInvariants(unittest.TestCase):

    def test_fresh_checkout_source_version_matches_package_version(self):
        self.assertEqual(sourcelib.read_version(REPO), ainative.__version__)
        self.assertEqual(read_version(REPO), ainative.__version__)
        self.assertEqual(package_version(REPO), ainative.__version__)
        self.assertEqual(assert_version_consistency(REPO), ainative.__version__)

    def test_the_agents_md_stack_version_marker_matches_the_release(self):
        marker = re.search(r"stack-version:\s*([0-9][0-9A-Za-z.\-]*)",
                           (REPO / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIsNotNone(marker, "AGENTS.md lost its stack-version header")
        self.assertEqual(marker.group(1), ainative.__version__,
                         "UPDATING.md moves VERSION and the AGENTS.md header together")
    def test_packaged_metadata_derives_from_the_package_version(self):
        pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('version = { attr = "ainative.__version__" }', pyproject)

    def test_the_staged_payload_carries_the_package_version(self):
        with tempfile.TemporaryDirectory(prefix="ainative-payload-") as staging:
            payload = stage_payload(REPO, Path(staging) / "payload")
            self.assertEqual(read_version(payload), ainative.__version__)

    def test_the_lifecycle_bundle_carries_the_package_version(self):
        scripts = REPO / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from build_lifecycle_bundle import build

        with tempfile.TemporaryDirectory(prefix="ainative-bundle-") as staging:
            bundle = build(Path(staging) / "dist")
            self.assertEqual(bundle.name, f"ainative-dev-stack-{ainative.__version__}.zip")
            with zipfile.ZipFile(bundle) as archive:
                self.assertEqual(archive.read("VERSION").decode("utf-8").strip(),
                                 ainative.__version__)

    def test_two_disagreeing_labels_refuse_the_build(self):
        with tempfile.TemporaryDirectory(prefix="ainative-mismatch-") as staging:
            root = Path(staging)
            (root / "ainative").mkdir()
            write_text(root / "VERSION", "9.9.9\n")
            write_text(root / "ainative" / "__init__.py", '__version__ = "1.0.0"\n')
            with self.assertRaises(VersionMismatch):
                assert_version_consistency(root)


class WheelPayloadInvariants(unittest.TestCase):
    """The wheel's payload, built the way a PEP 517 frontend builds it.

    `pip wheel` performs an isolated build, so the test never depends on
    whichever setuptools sits in the runner environment: the macos and windows
    py3.11 runners ship one without a usable `bdist_wheel`, and delegating to
    it in-process failed there (first CI run of PR #130) while py3.13 and
    ubuntu passed. Isolation makes the result depend on the declared build
    requirements, not on the image.
    """

    def test_wheel_payload_version_matches_package_version(self):
        with tempfile.TemporaryDirectory(prefix="ainative-wheel-") as staging:
            output = Path(staging)
            completed = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--disable-pip-version-check",
                 "--no-deps", "--wheel-dir", str(output), str(REPO)],
                capture_output=True, text=True, timeout=900)
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            wheels = sorted(output.glob("*.whl"))
            self.assertTrue(wheels, completed.stdout[-1000:])
            with zipfile.ZipFile(wheels[0]) as archive:
                payload = archive.read("ainative/_payload/VERSION").decode("utf-8").strip()
                self.assertEqual(payload, ainative.__version__)
                metadata = next(entry for entry in archive.namelist()
                                if entry.endswith(".dist-info/METADATA"))
                head = archive.read(metadata).decode("utf-8")
                self.assertIn(f"Version: {ainative.__version__}", head)


@unittest.skipUnless(_has_setuptools(), "setuptools is not installed in this environment")
class BuildBackendRefusal(unittest.TestCase):

    def test_a_mismatched_tree_cannot_build_a_wheel(self):
        import _build_backend

        with tempfile.TemporaryDirectory(prefix="ainative-badbuild-") as staging:
            bad_root = Path(staging) / "tree"
            shutil.copytree(REPO / "ainative", bad_root / "ainative",
                            ignore=shutil.ignore_patterns("_payload", "__pycache__"))
            write_text(bad_root / "VERSION", "0.0.1\n")
            original = _build_backend.ROOT
            _build_backend.ROOT = bad_root
            try:
                with self.assertRaises(VersionMismatch):
                    _build_backend.stage_payload()
            finally:
                _build_backend.ROOT = original


if __name__ == "__main__":
    unittest.main()