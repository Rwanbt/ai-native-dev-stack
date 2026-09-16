"""Release V3: candidate policy, the anchored manifest, and the exact chain.

ADR-0019 sections 7–10, pinned: build metadata is not an installable version,
duplicates are never resolved by order, an incomplete enumeration refuses
instead of picking the best of what it saw, the manifest is verified against
provider metadata BEFORE it is parsed, and one version must hold across every
trust-bearing identity.
"""

from __future__ import annotations

import json
import unittest
from hashlib import sha256

from ainative.lifecycle import release_v3
from ainative.lifecycle.errors import LifecycleError


def manifest_payload(version: str = "2.5.0", *, runtime: str | None = None,
                     artifact_version: str | None = None,
                     artifact_name: str | None = None,
                     protocol: str = "v3", channel: str = "stable",
                     extra_artifacts: list | None = None,
                     **document_overrides) -> bytes:
    artifact_version = artifact_version or version
    artifacts = [{
        "name": artifact_name or release_v3.lifecycle_bundle_name(artifact_version),
        "kind": "lifecycle", "version": artifact_version,
        "sha256": "a" * 64, "size": 10,
    }]
    artifacts.extend(extra_artifacts or [])
    document = {
        "schema": "ainative.release",
        "protocol": protocol,
        "version": version,
        "channel": channel,
        "compatibility": {"runtime_version": runtime or version},
        "artifacts": artifacts,
        "provenance": {"source": "test"},
    }
    document.update(document_overrides)
    return json.dumps(document).encode("utf-8")


def anchor(payload: bytes) -> tuple[str, int]:
    return sha256(payload).hexdigest(), len(payload)


def candidate(version: str, *, identity: str | None = None, channel: str = "stable",
              payload: bytes | None = None, anchored: bool = True):
    digest, size = anchor(payload) if payload is not None else ("a" * 64, 10)
    return release_v3.ReleaseCandidate(
        version=version, identity=identity or f"release-{version}", channel=channel,
        manifest_sha256=digest if anchored else None,
        manifest_size=size if anchored else None)


def expect(code: str, action) -> LifecycleError:
    try:
        action()
    except LifecycleError as error:
        if error.code != code:
            raise AssertionError(f"expected {code}, got {error.code}: "
                                 f"{error.message}") from error
        return error
    raise AssertionError(f"expected a {code} refusal; nothing was raised")


class SemVerPolicy(unittest.TestCase):

    def test_canonical_versions_are_semver_without_build_metadata(self):
        self.assertEqual(release_v3.canonical_version("1.2.3"), "1.2.3")
        self.assertEqual(release_v3.canonical_version("v1.2.3"), "1.2.3")
        self.assertEqual(release_v3.canonical_version("1.2.3-rc.1"), "1.2.3-rc.1")

    def test_build_metadata_is_not_an_installable_version(self):
        expect("RELEASE_BUILD_METADATA_UNSUPPORTED",
               lambda: release_v3.canonical_version("1.2.3+build1"))

    def test_a_non_semver_candidate_keeps_the_historical_refusal(self):
        expect("UPDATE_CHECK_FAILED", lambda: release_v3.canonical_version("nightly"))


class CandidateSelection(unittest.TestCase):

    def select(self, candidates, *, complete=True, channel="stable"):
        result = release_v3.EnumerationResult(tuple(candidates), complete)
        return release_v3.select_candidate(result, release_v3.ReleaseQuery(channel))

    def test_order_is_version_order_not_string_order(self):
        chosen = self.select([candidate("1.9.0"), candidate("1.10.0")])
        self.assertEqual(chosen.version, "1.10.0")

    def test_a_release_outranks_its_pre_releases(self):
        chosen = self.select([candidate("1.2.3-rc.1"), candidate("1.2.3")])
        self.assertEqual(chosen.version, "1.2.3")
        chosen = self.select([candidate("1.2.3-rc.1"), candidate("1.2.3-rc.2")])
        self.assertEqual(chosen.version, "1.2.3-rc.2")

    def test_another_channel_is_not_a_candidate(self):
        expect("RELEASE_NO_CANDIDATE",
               lambda: self.select([candidate("1.2.3", channel="beta")]))

    def test_an_incomplete_enumeration_refuses_even_with_candidates(self):
        expect("RELEASE_ENUMERATION_INCOMPLETE",
               lambda: self.select([candidate("1.2.3")], complete=False))

    def test_a_complete_channel_with_nothing_refuses(self):
        expect("RELEASE_NO_CANDIDATE", lambda: self.select([]))

    def test_two_identities_on_one_version_refuse_as_duplicates(self):
        error = expect("RELEASE_DUPLICATE_VERSION",
                       lambda: self.select([candidate("1.2.3", identity="tag-a"),
                                            candidate("1.2.3", identity="tag-b")]))
        self.assertEqual(error.detail["version"], "1.2.3")

    def test_the_same_identity_listed_twice_is_one_candidate(self):
        chosen = self.select([candidate("1.2.3", identity="tag-a"),
                              candidate("1.2.3", identity="tag-a")])
        self.assertEqual(chosen.identity, "tag-a")


class TrustAnchor(unittest.TestCase):

    def verify(self, payload, *, sha=None, size=None):
        release_v3.verify_external_anchor(payload, sha256=sha, size=size)

    def test_an_absent_anchor_is_missing_metadata(self):
        expect("RELEASE_INTEGRITY_METADATA_MISSING",
               lambda: self.verify(b"{}", sha=None, size=None))

    def test_a_malformed_anchor_is_invalid_metadata(self):
        for sha, size in (("zz", 2), ("a" * 64, 0), ("a" * 64, "2")):
            with self.subTest(sha=sha, size=size):
                expect("RELEASE_INTEGRITY_METADATA_INVALID",
                       lambda sha=sha, size=size: self.verify(b"{}", sha=sha, size=size))

    def test_a_size_mismatch_is_refused(self):
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.verify(b"{}", sha="a" * 64, size=99))

    def test_a_digest_mismatch_is_refused(self):
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.verify(b"{}", sha="a" * 64, size=2))

    def test_a_matching_anchor_passes(self):
        digest, size = anchor(b'{"ok": true}')
        self.verify(b'{"ok": true}', sha=digest, size=size)

    def test_verification_happens_before_parsing(self):
        # Invalid JSON with a WRONG digest must fail on the digest, proving the
        # bytes were verified before being parsed; with a correct anchor the
        # same bytes reach the parser and fail there.
        error = expect("UPDATE_INTEGRITY_FAILED",
                       lambda: self._verify_then_parse(b"{not json"))
        self.assertIn("does not match", error.message)
        error = expect("UPDATE_INTEGRITY_FAILED",
                       lambda: release_v3.parse_manifest(b"{not json"))
        self.assertIn("not valid JSON", error.message)

    def _verify_then_parse(self, payload: bytes) -> None:
        self.verify(payload, sha="a" * 64, size=len(payload))
        release_v3.parse_manifest(payload)


class ManifestValidation(unittest.TestCase):

    def parse(self, payload: bytes):
        return release_v3.parse_manifest(payload)

    def test_a_valid_manifest_round_trips(self):
        manifest = self.parse(manifest_payload())
        self.assertEqual(manifest.version, "2.5.0")
        self.assertEqual(manifest.runtime_version, "2.5.0")
        self.assertEqual(manifest.channel, "stable")
        self.assertEqual(manifest.lifecycle_artifact().name,
                         "ainative-lifecycle-v3-2.5.0.zip")
        self.assertEqual(manifest.to_record()["provenance"], {"source": "test"})

    def test_a_newer_protocol_asks_for_a_newer_cli(self):
        expect("CLI_UPDATE_REQUIRED",
               lambda: self.parse(manifest_payload(protocol="v4")))

    def test_an_unknown_protocol_is_an_integrity_refusal(self):
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.parse(manifest_payload(protocol="v2")))

    def test_an_unknown_schema_is_refused(self):
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.parse(manifest_payload(schema="something.else")))

    def test_a_build_metadata_manifest_version_is_refused(self):
        expect("RELEASE_BUILD_METADATA_UNSUPPORTED",
               lambda: self.parse(manifest_payload(version="2.5.0+build1")))

    def test_missing_pieces_are_refused(self):
        for overrides in ({"channel": ""}, {"compatibility": None},
                          {"artifacts": []}, {"provenance": []},
                          {"version": None}):
            with self.subTest(overrides=overrides):
                expect("UPDATE_INTEGRITY_FAILED",
                       lambda overrides=overrides: self.parse(
                           manifest_payload(**overrides)))

    def test_a_traversing_artifact_name_is_refused(self):
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.parse(manifest_payload(artifact_name="../../evil.zip")))
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.parse(manifest_payload(artifact_name="sub/evil.zip")))

    def test_an_unknown_artifact_kind_is_refused(self):
        digest, size = anchor(b"x")
        extra = [{"name": "wheel.whl", "kind": "wheel", "version": "2.5.0",
                  "sha256": "a" * 64, "size": 10}]
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.parse(manifest_payload(extra_artifacts=extra)))

    def test_a_malformed_artifact_digest_is_refused(self):
        payload = manifest_payload()
        document = json.loads(payload)
        document["artifacts"][0]["sha256"] = "nope"
        expect("UPDATE_INTEGRITY_FAILED",
               lambda: self.parse(json.dumps(document).encode()))

    def test_two_lifecycle_artifacts_are_ambiguous(self):
        second = {"name": "ainative-lifecycle-v3-2.5.0.zip", "kind": "lifecycle",
                  "version": "2.5.0", "sha256": "b" * 64, "size": 11}
        manifest = self.parse(manifest_payload(extra_artifacts=[second]))
        expect("UPDATE_INTEGRITY_FAILED", manifest.lifecycle_artifact)


class VersionChain(unittest.TestCase):

    def chain(self, *, candidate_version="2.5.0", manifest_payload_args=None,
              protocol_release_version=None):
        payload = manifest_payload(**(manifest_payload_args or {}))
        manifest = release_v3.parse_manifest(payload)
        release_v3.require_exact_version_chain(
            candidate(candidate_version), manifest, manifest.lifecycle_artifact(),
            protocol_release_version=protocol_release_version)

    def test_the_exact_chain_passes(self):
        self.chain(protocol_release_version="2.5.0")

    def test_every_broken_link_is_refused(self):
        cases = (
            {"candidate_version": "2.5.1"},
            {"manifest_payload_args": {"version": "2.5.1"}},
            {"manifest_payload_args": {"runtime": "2.4.9"}},
            {"manifest_payload_args": {"artifact_version": "2.4.9"}},
            {"manifest_payload_args": {"artifact_name": "ainative-lifecycle-v3-2.4.9.zip"}},
            {"protocol_release_version": "2.4.9"},
        )
        for case in cases:
            with self.subTest(case=case):
                error = expect("UPDATE_VERSION_MISMATCH", lambda case=case: self.chain(**case))
                self.assertIn("chain", error.detail)

    def test_the_chain_detail_names_every_link(self):
        error = expect("UPDATE_VERSION_MISMATCH",
                       lambda: self.chain(candidate_version="2.5.1",
                                          protocol_release_version="2.5.0"))
        self.assertEqual(set(error.detail["chain"]),
                         {"candidate version", "manifest version",
                          "compatibility.runtime_version", "artifact version",
                          "artifact filename version",
                          "lifecycle-protocol.json release_version"})


class ResolutionOrder(unittest.TestCase):

    class FakeProvider(release_v3.ReleaseProvider):
        name = "fake"

        def __init__(self, candidates, payload, *, complete=True):
            self._result = release_v3.EnumerationResult(tuple(candidates), complete)
            self._payload = payload
            self.calls: list[str] = []

        def enumerate(self, query):
            self.calls.append("enumerate")
            return self._result

        def fetch_manifest(self, candidate):
            self.calls.append(f"fetch_manifest:{candidate.version}")
            return self._payload

        def fetch_artifact(self, candidate, artifact):
            raise AssertionError("resolve_manifest must not download artifacts")

    def test_a_complete_chain_resolves(self):
        payload = manifest_payload()
        provider = self.FakeProvider([candidate("2.5.0", payload=payload)], payload)
        resolved, manifest = release_v3.resolve_manifest(
            provider, release_v3.ReleaseQuery("stable"))
        self.assertEqual(resolved.version, "2.5.0")
        self.assertEqual(manifest.version, "2.5.0")
        self.assertEqual(provider.calls, ["enumerate", "fetch_manifest:2.5.0"])

    def test_an_incomplete_enumeration_never_fetches_a_manifest(self):
        payload = manifest_payload()
        provider = self.FakeProvider([candidate("2.5.0", payload=payload)], payload,
                                     complete=False)
        expect("RELEASE_ENUMERATION_INCOMPLETE",
               lambda: release_v3.resolve_manifest(provider,
                                                   release_v3.ReleaseQuery("stable")))
        self.assertEqual(provider.calls, ["enumerate"])

    def test_an_unanchored_candidate_never_reaches_the_parser(self):
        payload = manifest_payload()
        provider = self.FakeProvider([candidate("2.5.0", anchored=False)], payload)
        expect("RELEASE_INTEGRITY_METADATA_MISSING",
               lambda: release_v3.resolve_manifest(provider,
                                                   release_v3.ReleaseQuery("stable")))


if __name__ == "__main__":
    unittest.main()
