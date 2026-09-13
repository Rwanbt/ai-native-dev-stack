"""The official update path: a real published artifact, a real digest, no fallback.

v2.2.0 published no lifecycle bundle, so `_select_asset()` fell back to the
`zipball_url` with `digest = None` and `verify_archive()` compared nothing
(#126). These tests drive the official provider against release documents with
the exact shape the GitHub Releases API serves — driven without the network —
and pin every refusal:

* the release-shaped document selects the lifecycle bundle and its digest;
* one flipped byte refuses with UPDATE_INTEGRITY_FAILED and zero project writes;
* a bundle without a published digest refuses with
  UPDATE_INTEGRITY_METADATA_MISSING;
* a document with only `zipball_url` refuses: no silent unverified path;
* the full official E2E — select, download, verify, extract, plan, transaction —
  reaches the target version and leaves a rollback available.
"""

from __future__ import annotations

import json
import sys
import unittest
from hashlib import sha256
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tests.lifecycle_support import (LifecycleTestCase, build_distribution_tree,
                                     make_release_archive)
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import state as statelib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle.errors import LifecycleError

BUNDLE_NAME = "ainative-dev-stack-2.0.0.zip"
BUNDLE_URL = "https://example.invalid/ainative-dev-stack-2.0.0.zip"
RELEASE_URL = "https://example.invalid/releases/latest"


class OfficialReleaseDocument(LifecycleTestCase):
    """A GitHub-shaped release document, with the transport stubbed out."""

    def setUp(self) -> None:
        super().setUp()
        self.install("standard")
        self.assume_runtime("2.0.0")
        self.v2_tree = build_distribution_tree(self.root / "dist-v2", "2.0.0")
        self.archive = make_release_archive(self.v2_tree, self.root / "bundle-2.0.0.zip")
        self.archive_bytes = self.archive.read_bytes()
        self.digest = sha256(self.archive_bytes).hexdigest()
    # --- fixtures --------------------------------------------------------

    def document(self, *, digest: str | None = "match", include_bundle: bool = True,
                 include_zipball: bool = True) -> bytes:
        assets = []
        if include_bundle:
            asset = {"name": BUNDLE_NAME, "browser_download_url": BUNDLE_URL,
                     "size": len(self.archive_bytes)}
            if digest == "match":
                asset["digest"] = f"sha256:{self.digest}"
            elif digest is not None:
                asset["digest"] = digest
            assets.append(asset)
        document = {"tag_name": "v2.0.0", "assets": assets}
        if include_zipball:
            document["zipball_url"] = "https://example.invalid/zipball/v2.0.0"
        return json.dumps(document).encode("utf-8")

    def provider(self, document: bytes, archive: bytes | None = None):
        provider = providerlib.ReleaseApiProvider(RELEASE_URL)
        responses = {RELEASE_URL: document}
        if archive is not None:
            responses[BUNDLE_URL] = archive

        def fake_get(url: str, limit: int) -> bytes:
            if url not in responses:
                raise AssertionError(f"unexpected URL fetched: {url}")
            return responses[url]

        provider._get = fake_get
        return provider

    def snapshot(self) -> dict[str, str]:
        from ainative.lifecycle.digest import digest_file

        # A refused update writes nothing at all - not a file, not the check
        # cache (the updater records no cache before the version gates).
        return {path.relative_to(self.project).as_posix(): digest_file(path) or ""
                for path in self.project.rglob("*") if path.is_file()}
    # --- selection and refusal ------------------------------------------

    def test_the_lifecycle_bundle_and_its_published_digest_are_selected(self):
        release = self.provider(self.document()).latest("stable")
        self.assertEqual(release.version, "2.0.0")
        self.assertEqual(release.digest, self.digest)
        self.assertEqual(release.url, BUNDLE_URL)

    def test_a_bundle_without_a_published_digest_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            self.provider(self.document(digest=None)).latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")

    def test_a_malformed_published_digest_is_refused(self):
        with self.assertRaises(LifecycleError) as raised:
            self.provider(self.document(digest="sha256:not-a-digest")).latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")

    def test_only_a_zipball_is_refused_no_silent_unverified_path(self):
        document = self.document(include_bundle=False, include_zipball=True)
        with self.assertRaises(LifecycleError) as raised:
            self.provider(document).latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")
        self.assertIn("lifecycle bundle", raised.exception.message)

    def test_a_release_with_nothing_to_consume_is_refused(self):
        document = self.document(include_bundle=False, include_zipball=False)
        with self.assertRaises(LifecycleError) as raised:
            self.provider(document).latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")

    def test_verify_archive_refuses_a_missing_digest(self):
        with self.assertRaises(LifecycleError) as raised:
            providerlib.verify_archive(b"payload", None)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")
    # --- the mutation probe and the E2E ---------------------------------

    def test_one_flipped_byte_refuses_before_any_write(self):
        mutated = bytearray(self.archive_bytes)
        mutated[-1] ^= 0xFF
        provider = self.provider(self.document(), bytes(mutated))
        before = self.snapshot()
        with mock.patch.object(providerlib, "build", lambda channel="stable": provider):
            with self.assertRaises(LifecycleError) as raised:
                updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")
        self.assertEqual(self.snapshot(), before, "a refused update touched the project")
        self.assertFalse(self.exists("AGENTS.md.new"))

    def test_the_official_path_updates_end_to_end(self):
        provider = self.provider(self.document(), self.archive_bytes)
        with mock.patch.object(providerlib, "build", lambda channel="stable": provider):
            result = updaterlib.apply(self.project, distribution=self.distribution)
        self.assertTrue(result.applied)
        self.assertEqual(result.to_version, "2.0.0")
        self.assertEqual(self.read("AGENTS.md"), "# Engineering method 2.0.0\n")
        state = statelib.load(self.project)
        self.assertEqual(state.stack_version, "2.0.0")
        self.assertEqual(state.source_version, "2.0.0")
        self.assertTrue(result.rollback_available)


class LocalMirrorIntegrity(LifecycleTestCase):

    def test_a_local_index_without_a_digest_is_refused(self):
        releases = self.root / "releases"
        releases.mkdir()
        (releases / "releases.json").write_text(json.dumps(
            {"channels": {"stable": {"version": "2.0.0", "archive": "stack.zip"}}}),
            encoding="utf-8")
        provider = providerlib.LocalDirectoryProvider(releases)
        with self.assertRaises(LifecycleError) as raised:
            provider.latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")


if __name__ == "__main__":
    unittest.main()