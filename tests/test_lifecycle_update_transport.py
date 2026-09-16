"""Update transport: credential confinement, authenticated checks, protocol v2.

The token an environment offers (`GITHUB_TOKEN`/`GH_TOKEN`) exists to raise the
anonymous GitHub API rate limit. Before this suite existed, `_get()` attached it
to every request it made - including an artifact URL named by the release
metadata of a custom `AINATIVE_UPDATE_URL` - and urllib's redirect handler
copied `Authorization` to any redirect target. Any custom source could therefore
collect the user's provider token, and a legitimate-looking `302` could hand it
to an unrelated host.

These tests pin the confinement rule instead: a credential is sent only to the
origin it belongs to, never across an origin boundary, never to the anonymous
`AINATIVE_UPDATE_URL` selector, and never after an `https -> http` downgrade.
The protocol v2 containment tests at the end are unchanged: a legacy runtime
(<= v2.2.2) must not be able to consume a protocol v2 bundle even when a mirror
names the file for it - the *layout* refuses it, not just the asset selector.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

from tests.lifecycle_support import LifecycleTestCase
from ainative.lifecycle import provider as providerlib
from ainative.lifecycle import transport as transportlib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle.errors import LifecycleError

TOKEN = "ghp_" + "x" * 36
APPROVED_ORIGIN = "https://api.github.com"
ASSET_API_URL = "https://api.github.com/repos/o/r/releases/assets/5"
BUNDLE_NAME = "ainative-lifecycle-v2-2.0.0.zip"


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class FakeResponse:
    """The part of an HTTP response this transport consumes, and nothing more."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class ScriptedTransport:
    """Answers a scripted hop table; records (url, Authorization, Accept) per hop.

    A hop is either the bytes to serve or `("redirect", location)`. An
    unscripted URL raises: a request the test did not anticipate is a failure,
    not a silent network attempt.
    """

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

    def authorizations(self) -> list[tuple[str, str | None]]:
        return [(origin(url), authorization) for url, authorization, _ in self.observed]


class CredentialConfinement(unittest.TestCase):
    """One rule: a credential goes exactly where it belongs, and nowhere else."""

    def setUp(self) -> None:
        for name in (*providerlib.TOKEN_ENVS, providerlib.RELEASE_URL_ENV, "GITLAB_TOKEN"):
            previous = os.environ.pop(name, None)
            if previous is not None:
                self.addCleanup(os.environ.__setitem__, name, previous)

    def get(self, provider, server: ScriptedTransport, url: str,
            limit: int = 1_000_000) -> bytes:
        with mock.patch.object(transportlib, "_send", server.send):
            return provider._get(url, limit)

    # --- where the credential may go ------------------------------------

    def test_the_trusted_github_api_receives_the_bearer(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({providerlib.DEFAULT_RELEASE_URL: b"{}"})
        self.assertEqual(self.get(provider, server, providerlib.DEFAULT_RELEASE_URL), b"{}")
        self.assertEqual(server.observed[0][1], f"Bearer {TOKEN}")

    def test_no_token_means_no_authorization_header(self):
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({providerlib.DEFAULT_RELEASE_URL: b"{}"})
        self.get(provider, server, providerlib.DEFAULT_RELEASE_URL)
        self.assertIsNone(server.observed[0][1])

    def test_a_custom_url_never_receives_the_bearer(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider("https://evil.example/releases/latest")
        server = ScriptedTransport({"https://evil.example/releases/latest": b"{}"})
        self.get(provider, server, provider.url)
        self.assertIsNone(server.observed[0][1],
                          "a custom source received the provider credential")

    def test_ainative_update_url_is_anonymous_even_at_the_api_host(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        os.environ["GH_TOKEN"] = TOKEN
        os.environ["GITLAB_TOKEN"] = TOKEN
        url = "https://api.github.com/repos/Rwanbt/ai-native-dev-stack/releases/latest"
        os.environ[providerlib.RELEASE_URL_ENV] = url
        provider = providerlib.ReleaseApiProvider()
        self.assertEqual(provider.url, url)
        server = ScriptedTransport({url: b"{}"})
        self.get(provider, server, url)
        self.assertIsNone(server.observed[0][1],
                          "AINATIVE_UPDATE_URL must never carry a provider credential")

    # --- URLs the transport refuses outright -----------------------------

    def test_a_url_with_embedded_credentials_is_refused(self):
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({})
        with self.assertRaises(LifecycleError) as raised:
            self.get(provider, server, "https://user:secret@api.github.com/releases/latest")
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertNotIn("secret", raised.exception.message)

    def test_a_non_https_url_is_refused(self):
        provider = providerlib.ReleaseApiProvider("http://example.invalid/releases")
        with self.assertRaises(LifecycleError) as raised:
            provider.latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")

    # --- redirects --------------------------------------------------------

    def test_a_same_origin_metadata_redirect_keeps_the_bearer(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider()
        first = providerlib.DEFAULT_RELEASE_URL
        second = "https://api.github.com/repos/x/y/releases/1234"
        server = ScriptedTransport({first: ("redirect", "/repos/x/y/releases/1234"),
                                    second: b'{"ok": true}'})
        self.assertEqual(self.get(provider, server, first), b'{"ok": true}')
        self.assertEqual(server.authorizations(),
                         [(APPROVED_ORIGIN, f"Bearer {TOKEN}"),
                          (APPROVED_ORIGIN, f"Bearer {TOKEN}")])

    def test_a_cross_origin_metadata_redirect_is_refused(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({
            providerlib.DEFAULT_RELEASE_URL: ("redirect", "https://evil.example/metadata")})
        with self.assertRaises(LifecycleError) as raised:
            self.get(provider, server, providerlib.DEFAULT_RELEASE_URL)
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertEqual(len(server.observed), 1, "the redirect target was contacted")

    def test_an_https_to_http_redirect_is_refused(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({
            providerlib.DEFAULT_RELEASE_URL: ("redirect", "http://mirror.example/releases")})
        with self.assertRaises(LifecycleError) as raised:
            self.get(provider, server, providerlib.DEFAULT_RELEASE_URL)
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertEqual(len(server.observed), 1, "a downgraded hop was attempted")

    def test_a_redirect_target_with_embedded_credentials_is_refused(self):
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({
            providerlib.DEFAULT_RELEASE_URL:
                ("redirect", "https://user:secret@api.github.com/releases/2")})
        with self.assertRaises(LifecycleError) as raised:
            self.get(provider, server, providerlib.DEFAULT_RELEASE_URL)
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertEqual(len(server.observed), 1)

    def test_a_redirect_loop_is_refused(self):
        provider = providerlib.ReleaseApiProvider()
        url = providerlib.DEFAULT_RELEASE_URL
        server = ScriptedTransport({url: ("redirect", url)})
        with self.assertRaises(LifecycleError) as raised:
            self.get(provider, server, url)
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertEqual(len(server.observed), transportlib.MAX_REDIRECTS + 1)

    def test_an_oversized_response_is_refused(self):
        provider = providerlib.ReleaseApiProvider()
        server = ScriptedTransport({providerlib.DEFAULT_RELEASE_URL: b"x" * 2_000})
        with self.assertRaises(LifecycleError) as raised:
            self.get(provider, server, providerlib.DEFAULT_RELEASE_URL, 1_000)
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_FAILED")

    def test_a_rate_limited_check_says_so_without_echoing_the_token(self):
        os.environ["GH_TOKEN"] = "github_pat_secret_value"
        provider = providerlib.ReleaseApiProvider()

        def send(request):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        with mock.patch.object(transportlib, "_send", send):
            with self.assertRaises(LifecycleError) as raised:
                provider._get(providerlib.DEFAULT_RELEASE_URL, 100)
        self.assertEqual(raised.exception.code, "UPDATE_CHECK_FAILED")
        self.assertIn("rate-limited", raised.exception.message)
        self.assertNotIn("github_pat_secret_value", raised.exception.message)

    # --- artifacts: the CDN hop is anonymous ------------------------------

    def test_the_asset_api_redirect_to_the_cdn_strips_the_bearer(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider()
        cdn = "https://objects.githubusercontent.com/blob/xyz"
        server = ScriptedTransport({ASSET_API_URL: ("redirect", cdn),
                                    cdn: b"payload-bytes"})
        with mock.patch.object(transportlib, "_send", server.send):
            payload = provider._fetch_artifact(ASSET_API_URL, 1_000)
        self.assertEqual(payload, b"payload-bytes")
        self.assertEqual(server.observed[0][1], f"Bearer {TOKEN}")
        self.assertEqual(server.observed[0][2], transportlib.ACCEPT_OCTET_STREAM)
        self.assertIsNone(server.observed[1][1],
                          "the CDN received the provider credential")

    # --- the gate: no credential anywhere else ----------------------------

    def test_no_credential_reaches_a_non_approved_origin_across_the_flow(self):
        os.environ["GITHUB_TOKEN"] = TOKEN
        provider = providerlib.ReleaseApiProvider()
        cdn = "https://objects.githubusercontent.com/blob"
        document = {"tag_name": "v2.0.0", "assets": [{
            "name": BUNDLE_NAME, "url": ASSET_API_URL,
            "browser_download_url": f"https://github.com/o/r/releases/download/v2.0.0/{BUNDLE_NAME}",
            "digest": "sha256:" + "0" * 64}]}
        server = ScriptedTransport({
            providerlib.DEFAULT_RELEASE_URL: json.dumps(document).encode(),
            ASSET_API_URL: ("redirect", cdn), cdn: b"bundle"})
        with mock.patch.object(transportlib, "_send", server.send):
            release = provider.latest("stable")
            self.assertEqual(release.url, ASSET_API_URL)
            self.assertEqual(provider.fetch(release), b"bundle")
        self.assertEqual(len(server.observed), 3, server.observed)
        for url, authorization, _accept in server.observed:
            if origin(url) == APPROVED_ORIGIN:
                self.assertEqual(authorization, f"Bearer {TOKEN}", url)
            else:
                self.assertIsNone(authorization, f"credential sent to {url}")


class GitHubPrivateAssetFlow(unittest.TestCase):
    """A private asset is fetched through the asset API, never the browser URL."""

    def provider(self, document: dict) -> providerlib.ReleaseApiProvider:
        provider = providerlib.ReleaseApiProvider()
        provider._get = lambda url, limit: json.dumps(document).encode("utf-8")
        return provider

    def test_the_asset_api_url_is_selected_when_published(self):
        document = {"tag_name": "v2.0.0", "assets": [{
            "name": BUNDLE_NAME, "url": ASSET_API_URL,
            "browser_download_url": f"https://github.com/o/r/releases/download/v2.0.0/{BUNDLE_NAME}",
            "digest": "sha256:" + "0" * 64}]}
        release = self.provider(document).latest("stable")
        self.assertEqual(release.url, ASSET_API_URL)
        self.assertEqual(release.digest, "0" * 64)

    def test_a_document_without_the_api_url_keeps_the_browser_url(self):
        document = {"tag_name": "v2.0.0", "assets": [{
            "name": BUNDLE_NAME,
            "browser_download_url": f"https://example.invalid/{BUNDLE_NAME}",
            "digest": "sha256:" + "0" * 64}]}
        release = self.provider(document).latest("stable")
        self.assertEqual(release.url, f"https://example.invalid/{BUNDLE_NAME}")

    def test_a_plain_http_asset_url_is_ignored_not_authenticated(self):
        document = {"tag_name": "v2.0.0", "assets": [{
            "name": BUNDLE_NAME, "browser_download_url": "http://evil.example/x.zip",
            "digest": "sha256:" + "0" * 64}]}
        with self.assertRaises(LifecycleError) as raised:
            self.provider(document).latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")


class FutureProtocolBridge(LifecycleTestCase):
    """A newer lifecycle protocol is a newer release, not a broken one (#157).

    Before this bridge existed, a V2 runtime meeting a V3 publication said
    `UPDATE_INTEGRITY_METADATA_MISSING` - "no lifecycle bundle to verify" -
    which sends every user looking for a publishing defect instead of upgrading
    the CLI. The two situations are now distinct: a future-protocol
    publication refuses with `CLI_UPDATE_REQUIRED` and the upgrade path, while
    a release that simply publishes no lifecycle bundle keeps the integrity
    refusal.
    """

    def v3_document(self, *, tag: str = "v3.0.0", extra_assets: list | None = None) -> bytes:
        assets = [
            {"name": "ainative-release-v3.json",
             "browser_download_url": "https://example.invalid/ainative-release-v3.json"},
            {"name": f"ainative-lifecycle-v3-{tag.lstrip('v')}.zip",
             "browser_download_url": f"https://example.invalid/ainative-lifecycle-v3-{tag.lstrip('v')}.zip"},
        ]
        assets.extend(extra_assets or [])
        return json.dumps({"tag_name": tag, "assets": assets}).encode("utf-8")

    def provider(self, document: bytes):
        provider = providerlib.ReleaseApiProvider("https://example.invalid/releases/latest")
        provider._get = lambda url, limit: document
        return provider

    def snapshot(self) -> dict:
        from ainative.lifecycle.digest import digest_file

        return {path.relative_to(self.project).as_posix(): digest_file(path) or ""
                for path in self.project.rglob("*") if path.is_file()}

    def test_a_future_protocol_release_is_refused_as_cli_update_required(self):
        with self.assertRaises(LifecycleError) as raised:
            self.provider(self.v3_document()).latest("stable")
        self.assertEqual(raised.exception.code, "CLI_UPDATE_REQUIRED")
        self.assertEqual(raised.exception.detail.get("target_version"), "3.0.0")
        self.assertIn("Upgrade the CLI first", raised.exception.message)
        self.assertIn("@v3.0.0", raised.exception.detail["upgrade_command"])

    def test_a_release_publishing_nothing_consumable_keeps_the_integrity_refusal(self):
        document = json.dumps({"tag_name": "v3.0.0", "assets": [
            {"name": "notes.txt", "browser_download_url": "https://example.invalid/notes.txt"}]}
        ).encode("utf-8")
        with self.assertRaises(LifecycleError) as raised:
            self.provider(document).latest("stable")
        self.assertEqual(raised.exception.code, "UPDATE_INTEGRITY_METADATA_MISSING")

    def test_a_bridge_style_release_stays_selectable_by_the_v2_runtime(self):
        """A release carrying both a V2 bundle and V3 markers is still a V2 release."""

        bundle = {"name": "ainative-lifecycle-v2-2.5.0.zip",
                  "browser_download_url": "https://example.invalid/ainative-lifecycle-v2-2.5.0.zip",
                  "digest": "sha256:" + "a" * 64}
        document = self.v3_document(tag="v2.5.0", extra_assets=[bundle])
        release = self.provider(document).latest("stable")
        self.assertEqual(release.version, "2.5.0")
        self.assertEqual(release.digest, "a" * 64)

    def test_check_reports_a_future_release_as_available_with_a_cli_upgrade(self):
        self.install("standard")
        provider = self.provider(self.v3_document())
        with mock.patch.object(providerlib, "build", lambda channel="stable": provider):
            result = updaterlib.check(self.project, force=True, record=False)
        self.assertEqual(result.status, updaterlib.UPDATE_AVAILABLE)
        self.assertEqual(result.latest, "3.0.0")
        self.assertFalse(result.runtime_ready)

    def test_apply_refuses_a_future_release_before_any_write(self):
        self.install("standard")
        provider = self.provider(self.v3_document())
        before = self.snapshot()
        with mock.patch.object(providerlib, "build", lambda channel="stable": provider):
            with self.assertRaises(LifecycleError) as raised:
                updaterlib.apply(self.project, distribution=self.distribution)
        self.assertEqual(raised.exception.code, "CLI_UPDATE_REQUIRED")
        self.assertEqual(self.snapshot(), before, "a refused update touched the project")


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
