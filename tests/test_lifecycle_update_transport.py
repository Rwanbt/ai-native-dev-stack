"""Update transport: authenticated checks, rate-limit reporting, protocol v2.

The anonymous GitHub check is rate-limited per IP, and many users share one
NAT; a `GITHUB_TOKEN`/`GH_TOKEN` must be usable without ever being logged or
persisted. A legacy runtime (<= v2.2.2) must not be able to consume a protocol
v2 bundle even when a mirror names the file for it - the *layout* refuses it,
not just the official asset selector.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.lifecycle_support import LifecycleTestCase, write_text
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle.errors import LifecycleError


class AuthenticatedChecks(unittest.TestCase):

    def tearDown(self):
        for name in providerlib.TOKEN_ENVS:
            os.environ.pop(name, None)
        super().tearDown()

    def test_a_token_in_the_environment_is_sent_as_a_header(self):
        os.environ["GITHUB_TOKEN"] = "ghp_" + "x" * 36
        captured = {}

        class Response:
            status = 200

            def read(self, limit):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return Response()

        with mock.patch.object(providerlib.urllib.request, "urlopen", fake_urlopen):
            providerlib.ReleaseApiProvider("https://example.invalid")._get(
                "https://example.invalid", 100)
        self.assertEqual(captured["headers"].get("Authorization"),
                         "Bearer ghp_" + "x" * 36)

    def test_no_token_means_no_authorization_header(self):
        captured = {}

        class Response:
            status = 200

            def read(self, limit):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout=None):
            captured["headers"] = dict(request.headers)
            return Response()

        with mock.patch.object(providerlib.urllib.request, "urlopen", fake_urlopen):
            providerlib.ReleaseApiProvider("https://example.invalid")._get(
                "https://example.invalid", 100)
        self.assertNotIn("Authorization", captured["headers"])

    def test_a_rate_limited_check_says_so_without_echoing_the_token(self):
        os.environ["GH_TOKEN"] = "github_pat_secret_value"
        error = providerlib.urllib.error.HTTPError(
            "https://example.invalid", 403, "Forbidden", {}, None)

        def fake_urlopen(request, timeout=None):
            raise error

        with mock.patch.object(providerlib.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(LifecycleError) as raised:
                providerlib.ReleaseApiProvider("https://example.invalid")._get(
                    "https://example.invalid", 100)
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertIn("rate-limited", raised.exception.message)
        self.assertNotIn("github_pat_secret_value", raised.exception.message)


class ProtocolV2Containment(unittest.TestCase):
    """The layout, not the selector, is what a legacy runtime cannot consume."""

    def bundle(self, directory: Path) -> Path:
        path = directory / "ainative-lifecycle-v2-2.2.3.zip"
        protocol = {"schema_name": "lifecycle_protocol", "protocol_version": 2,
                    "release_version": "2.2.3", "payload_root": "stack"}
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("lifecycle-protocol.json", json.dumps(protocol))
            archive.writestr("protocol/README.md", "v2\n")
            archive.writestr("stack/VERSION", "2.2.3\n")
        return path

    def test_a_v1_root_finder_cannot_resolve_the_v2_layout(self):
        """Replays the <= 2.2.2 rule: VERSION at root, or one top-level dir."""

        with tempfile.TemporaryDirectory(prefix="v2-layout-") as staging:
            root = Path(staging)
            with zipfile.ZipFile(self.bundle(root)) as archive:
                archive.extractall(root / "extracted")
            extracted = root / "extracted"

            def v1_distribution_root():
                if (extracted / "VERSION").is_file():
                    return extracted
                children = [item for item in extracted.iterdir() if item.is_dir()]
                if len(children) == 1 and (children[0] / "VERSION").is_file():
                    return children[0]
                return None

            self.assertIsNone(v1_distribution_root(),
                              "a legacy runtime found a payload in the v2 layout")

    def test_the_current_runtime_resolves_and_validates_the_v2_layout(self):
        with tempfile.TemporaryDirectory(prefix="v2-layout-") as staging:
            root = Path(staging)
            with zipfile.ZipFile(self.bundle(root)) as archive:
                archive.extractall(root / "extracted")
            release = providerlib.Release(version="2.2.3", url=None,
                                          digest="0" * 64)
            payload = updaterlib._distribution_root(root / "extracted", release)
            self.assertEqual((payload / "VERSION").read_text(encoding="utf-8").strip(),
                             "2.2.3")

    def test_a_protocol_document_naming_another_release_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="v2-layout-") as staging:
            root = Path(staging)
            with zipfile.ZipFile(self.bundle(root)) as archive:
                archive.extractall(root / "extracted")
            other = providerlib.Release(version="9.9.9", url=None, digest="0" * 64)
            with self.assertRaises(LifecycleError) as raised:
                updaterlib._distribution_root(root / "extracted", other)
            self.assertEqual(raised.exception.code, "UPDATE_VERSION_MISMATCH")


class StrictCheck(LifecycleTestCase):

    def setUp(self):
        super().setUp()
        # Deterministic: a local provider with no index is unreachable by
        # construction. The default (GitHub) provider made this test depend on
        # the live release state - it passed while the API rate-limited the
        # runner and failed the moment a real release answered.
        self.set_env(providerlib.PROVIDER_ENV, "local")
        self.set_env(providerlib.LOCAL_SOURCE_ENV, str(self.root / "no-releases"))

    def test_strict_exits_non_zero_when_the_source_cannot_be_consulted(self):
        self.install("standard")
        completed = self.cli("update", "check", "--strict")
        self.assertEqual(completed.returncode, 1, completed.stdout)
        record = json.loads(self.cli("update", "check", "--strict", "--json").stdout)
        self.assertIn(record["status"], (updaterlib.OFFLINE, updaterlib.CHECK_FAILED))

    def test_without_strict_the_answer_is_exit_zero(self):
        self.install("standard")
        completed = self.cli("update", "check")
        self.assertEqual(completed.returncode, 0, completed.stdout)


if __name__ == "__main__":
    unittest.main()