"""The V3 providers: GitHub, the anonymous document, and the local mirror.

Providers fetch; release_v3 decides. These tests pin the fetching contract:
what is a candidate (drafts, non-SemVer tags and V2-era releases are not), how
the anchor travels from provider metadata, that a bounded listing says so, that
credentials follow the endpoint rule, and that the local mirror runs the same
logical verification chain as a network source.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.lifecycle_support import write_text
from ainative.lifecycle import release_providers as providerslib
from ainative.lifecycle import release_v3 as release_v3lib
from ainative.lifecycle import transport as transportlib
from ainative.lifecycle.errors import LifecycleError


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class ScriptedServer:
    def __init__(self, hops: dict) -> None:
        self.hops = hops
        self.observed: list[tuple[str, str | None, str | None]] = []

    def send(self, request: urllib.request.Request):
        url = request.full_url
        self.observed.append((url, request.get_header("Authorization"),
                              request.get_header("Accept")))
        if url not in self.hops:
            raise AssertionError(f"unexpected request: {url}")
        answer = self.hops[url]
        if isinstance(answer, tuple) and answer[0] == "redirect":
            raise urllib.error.HTTPError(url, 302, "Found",
                                         {"Location": answer[1]}, None)
        return FakeResponse(answer)


LIST_URL = "https://api.github.com/repos/o/r/releases?per_page=30"
MANIFEST_URL = "https://api.github.com/repos/o/r/releases/assets/1"


def release_document(version: str = "2.5.0", *, tag: str | None = None,
                     prerelease: bool = False, draft: bool = False,
                     manifest: bool = True, digest: str | None = "sha256:" + "a" * 64,
                     size: int | None = 10, artifact: bool = True) -> dict:
    tag = tag or f"v{version}"
    assets = []
    if manifest:
        asset = {"name": "ainative-release-v3.json", "url": MANIFEST_URL,
                 "browser_download_url": f"https://github.com/o/r/releases/download/{tag}/"
                                         "ainative-release-v3.json"}
        if digest is not None:
            asset["digest"] = digest
        if size is not None:
            asset["size"] = size
        assets.append(asset)
    if artifact:
        assets.append({"name": release_v3lib.lifecycle_bundle_name(version),
                       "url": "https://api.github.com/repos/o/r/releases/assets/2",
                       "digest": "sha256:" + "b" * 64, "size": 20})
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": assets}


def anchored_manifest(version: str = "2.5.0") -> bytes:
    document = {
        "schema": "ainative.release", "protocol": "v3", "version": version,
        "channel": "stable",
        "compatibility": {"runtime_version": version},
        "artifacts": [{"name": release_v3lib.lifecycle_bundle_name(version),
                       "kind": "lifecycle", "version": version,
                       "sha256": "b" * 64, "size": 20}],
        "provenance": {"source": "test"},
    }
    return json.dumps(document).encode("utf-8")


def github_provider(server: ScriptedServer, **kwargs):
    provider = providerslib.GitHubReleaseProvider(
        transportlib.GITHUB_ENDPOINT, repository="o/r", **kwargs)
    return provider, mock.patch.object(transportlib, "_send", server.send)


class GitHubEnumerate(unittest.TestCase):

    def enumerate(self, documents: list, **kwargs):
        bound = kwargs.get("page_bound", 30)
        server = ScriptedServer({
            f"https://api.github.com/repos/o/r/releases?per_page={bound}":
                json.dumps(documents).encode("utf-8")})
        provider, patcher = github_provider(server, **kwargs)
        with patcher:
            return provider.enumerate(release_v3lib.ReleaseQuery("stable"))

    def test_a_v3_release_becomes_a_candidate_with_its_anchor(self):
        result = self.enumerate([release_document()])
        self.assertTrue(result.complete)
        candidate = result.candidates[0]
        self.assertEqual(candidate.version, "2.5.0")
        self.assertEqual(candidate.identity, "v2.5.0")
        self.assertEqual(candidate.channel, "stable")
        self.assertEqual(candidate.manifest_sha256, "a" * 64)
        self.assertEqual(candidate.manifest_size, 10)
        self.assertEqual(candidate.manifest_locator, MANIFEST_URL)

    def test_drafts_prereleases_and_non_v3_releases_are_not_candidates(self):
        result = self.enumerate([
            release_document(draft=True),
            release_document(version="2.4.0", prerelease=True),
            release_document(version="2.3.0", manifest=False),
            release_document(version="2.2.0", tag="nightly"),
        ])
        self.assertEqual([candidate.version for candidate in result.candidates], ["2.4.0"])
        self.assertEqual(result.candidates[0].channel, "beta")

    def test_a_full_page_is_an_incomplete_enumeration(self):
        result = self.enumerate([release_document(), release_document(version="2.4.0")],
                                page_bound=2)
        self.assertFalse(result.complete)

    def test_a_missing_digest_is_carried_as_a_missing_anchor(self):
        result = self.enumerate([release_document(digest=None, size=None)])
        self.assertIsNone(result.candidates[0].manifest_sha256)
        self.assertIsNone(result.candidates[0].manifest_size)


class GitHubFetching(unittest.TestCase):

    def provider(self, server: ScriptedServer):
        return github_provider(server)

    def test_fetch_manifest_uses_the_locator_with_the_artifact_policy(self):
        manifest = anchored_manifest()
        server = ScriptedServer({
            LIST_URL: json.dumps([release_document()]).encode("utf-8"),
            MANIFEST_URL: manifest})
        provider, patcher = self.provider(server)
        with patcher, mock.patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_" + "x" * 36}):
            candidate = provider.enumerate(release_v3lib.ReleaseQuery("stable")).candidates[0]
            payload = provider.fetch_manifest(candidate)
        self.assertEqual(payload, manifest)
        self.assertEqual(server.observed[1][0], MANIFEST_URL)
        self.assertEqual(server.observed[1][1], "Bearer ghp_" + "x" * 36)
        self.assertEqual(server.observed[1][2], transportlib.ACCEPT_OCTET_STREAM)

    def test_fetch_artifact_picks_the_named_asset(self):
        server = ScriptedServer({
            LIST_URL: json.dumps([release_document()]).encode("utf-8"),
            "https://api.github.com/repos/o/r/releases/assets/2": b"bundle-bytes"})
        provider, patcher = self.provider(server)
        with patcher:
            candidate = provider.enumerate(release_v3lib.ReleaseQuery("stable")).candidates[0]
            payload = provider.fetch_artifact(
                candidate, release_v3lib.ManifestArtifact(
                    name=release_v3lib.lifecycle_bundle_name("2.5.0"), kind="lifecycle",
                    version="2.5.0", sha256="b" * 64, size=20))
        self.assertEqual(payload, b"bundle-bytes")

    def test_an_unknown_asset_is_refused(self):
        server = ScriptedServer({
            LIST_URL: json.dumps([release_document()]).encode("utf-8")})
        provider, patcher = self.provider(server)
        with patcher:
            candidate = provider.enumerate(release_v3lib.ReleaseQuery("stable")).candidates[0]
            with self.assertRaises(LifecycleError) as raised:
                provider.fetch_artifact(
                    candidate, release_v3lib.ManifestArtifact(
                        name="other.zip", kind="lifecycle", version="2.5.0",
                        sha256="b" * 64, size=1))
        self.assertEqual(raised.exception.code, "UPDATE_UNAVAILABLE")

    def test_fetching_before_enumerating_is_a_programming_refusal(self):
        provider = providerslib.GitHubReleaseProvider(transportlib.GITHUB_ENDPOINT,
                                                      repository="o/r")
        with self.assertRaises(LifecycleError) as raised:
            provider.fetch_manifest(release_v3lib.ReleaseCandidate(
                version="2.5.0", identity="v2.5.0"))
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")

    def test_resolve_manifest_runs_the_whole_chain(self):
        manifest = anchored_manifest()
        server = ScriptedServer({
            LIST_URL: json.dumps([release_document()]).encode("utf-8"),
            MANIFEST_URL: manifest})
        provider, patcher = self.provider(server)
        # The candidate's anchor must match the served manifest for the chain
        # to pass: rebuild the listing with the real digest and size.
        document = release_document(digest="sha256:" + sha256(manifest).hexdigest(),
                                    size=len(manifest))
        server.hops[LIST_URL] = json.dumps([document]).encode("utf-8")
        with patcher:
            candidate, parsed = release_v3lib.resolve_manifest(
                provider, release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(candidate.version, "2.5.0")
        self.assertEqual(parsed.version, "2.5.0")


class AnonymousDocument(unittest.TestCase):

    URL = "https://mirror.example/releases/latest"

    def provider(self, document: object):
        server = ScriptedServer({self.URL: json.dumps(document).encode("utf-8")})
        provider = providerslib.AnonymousReleaseApiProvider(self.URL)
        return provider, mock.patch.object(transportlib, "_send", server.send), server

    def test_a_v3_document_yields_one_candidate_and_no_credential(self):
        provider, patcher, server = self.provider(release_document())
        with patcher, mock.patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_" + "x" * 36}):
            result = provider.enumerate(release_v3lib.ReleaseQuery("stable"))
        self.assertTrue(result.complete)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(server.observed[0][1], None,
                         "the anonymous source received a credential")

    def test_a_v2_document_yields_no_candidate(self):
        provider, patcher, _server = self.provider(release_document(manifest=False))
        with patcher:
            result = provider.enumerate(release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(result.candidates, ())
        with self.assertRaises(LifecycleError) as raised:
            release_v3lib.select_candidate(result, release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(raised.exception.code, "RELEASE_NO_CANDIDATE")


class LocalMirror(unittest.TestCase):

    VERSION = "2.5.0"

    def setUp(self) -> None:
        self.directory = TemporaryDirectory(prefix="ainative-mirror-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = anchored_manifest(self.VERSION)
        write_text(self.root / self.VERSION / "ainative-release-v3.json", self.manifest.decode())
        write_text(self.root / self.VERSION / release_v3lib.lifecycle_bundle_name(self.VERSION),
                   "bundle-bytes\n")
        self.publish()

    def publish(self, *, sha: str | None = None, size: int | None = None,
                version: str = "2.5.0") -> None:
        payload = {"channels": {"stable": {
            "version": version,
            "manifest": {
                "file": "ainative-release-v3.json",
                "size": size if size is not None else len(self.manifest),
                "sha256": sha if sha is not None else sha256(self.manifest).hexdigest(),
            }}}}
        write_text(self.root / "releases.json", json.dumps(payload))

    def provider(self) -> providerslib.LocalReleaseProvider:
        return providerslib.LocalReleaseProvider(self.root)

    def test_the_whole_chain_runs_on_a_local_mirror(self):
        candidate, manifest = release_v3lib.resolve_manifest(
            self.provider(), release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(candidate.version, self.VERSION)
        self.assertEqual(manifest.version, self.VERSION)
        payload = self.provider().fetch_artifact(candidate, manifest.lifecycle_artifact())
        self.assertEqual(payload, b"bundle-bytes\n")

    def test_a_tampered_manifest_is_refused_by_the_anchor(self):
        write_text(self.root / self.VERSION / "ainative-release-v3.json",
                   self.manifest.decode().replace("2.5.0", "2.5.1"))
        with self.assertRaises(LifecycleError) as raised:
            release_v3lib.resolve_manifest(self.provider(),
                                           release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")

    def test_a_v2_era_index_entry_is_not_a_candidate(self):
        result = self.provider().enumerate(release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(len(result.candidates), 1)
        write_text(self.root / "releases.json",
                   json.dumps({"channels": {"stable": {"version": "2.5.0",
                                                       "archive": "stack.zip",
                                                       "sha256": "0" * 64}}}))
        result = self.provider().enumerate(release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(result.candidates, ())
        with self.assertRaises(LifecycleError) as raised:
            release_v3lib.select_candidate(result, release_v3lib.ReleaseQuery("stable"))
        self.assertEqual(raised.exception.code, "RELEASE_NO_CANDIDATE")

    def test_a_traversing_locator_cannot_leave_the_mirror(self):
        candidate = release_v3lib.ReleaseCandidate(
            version=self.VERSION, identity="local:stable",
            manifest_locator="../outside/ainative-release-v3.json")
        with self.assertRaises(LifecycleError) as raised:
            self.provider().fetch_manifest(candidate)
        self.assertEqual(raised.exception.code, "PATH_ESCAPE")

    def test_a_missing_artifact_is_refused(self):
        candidate = release_v3lib.ReleaseCandidate(
            version=self.VERSION, identity="local:stable")
        with self.assertRaises(LifecycleError) as raised:
            self.provider().fetch_artifact(
                candidate, release_v3lib.ManifestArtifact(
                    name="never-shipped.zip", kind="lifecycle", version=self.VERSION,
                    sha256="b" * 64, size=1))
        self.assertEqual(raised.exception.code, "UPDATE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
