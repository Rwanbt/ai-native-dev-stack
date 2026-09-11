import json
import unittest

from ainative.multivault.git_authority import (
    ApprovedGitRemote,
    FetchTransferEvidence,
    GitTransportPolicy,
    LastVerifiedRepositoryState,
    ObservedRepositoryIdentity,
    ObservedTransport,
    Visibility,
    build_fetch_evidence,
    compare_repository_state,
    normalize_remote_url,
    ref_is_allowed,
    unapproved_remotes,
    validate_remote,
    validate_transport,
)
from ainative.multivault.schema import SecurityClassification


def approved_remote(**overrides) -> ApprovedGitRemote:
    fields = {
        "canonical_fetch_url": "https://github.com/company/repo.git",
        "canonical_push_url": "git@github.com:company/repo.git",
        "provider_type": "github",
        "stable_repository_id": "R_kgDOAAAAAA",
        "required_owner_org": "company",
        "required_visibility_for_push": Visibility.PRIVATE,
        "allowed_refs": ("refs/heads/*",),
    }
    fields.update(overrides)
    return ApprovedGitRemote(**fields)


def observed_identity(**overrides) -> ObservedRepositoryIdentity:
    fields = {
        "provider_type": "github",
        "stable_repository_id": "R_kgDOAAAAAA",
        "owner_org": "company",
        "visibility": Visibility.PRIVATE,
        "effective_fetch_url": "https://github.com/company/repo.git",
        "effective_push_url": "git@github.com:company/repo.git",
    }
    fields.update(overrides)
    return ObservedRepositoryIdentity(**fields)


def transport_policy(**overrides) -> GitTransportPolicy:
    fields = {
        "protocol_allowlist": ("https", "ssh"),
        "transport_executable_identity": "git-2.51.1",
        "proxy": None,
        "ssh_command": None,
        "credential_helper": "store",
        "ssh_peer_policy": "pinned",
        "tls_peer_policy": "verified",
        "effective_transport_config_digest": "transport-digest",
    }
    fields.update(overrides)
    return GitTransportPolicy(**fields)


def observed_transport(**overrides) -> ObservedTransport:
    fields = {
        "protocol": "https",
        "transport_executable_identity": "git-2.51.1",
        "proxy": None,
        "ssh_command": None,
        "credential_helper": "store",
        "effective_transport_config_digest": "transport-digest",
    }
    fields.update(overrides)
    return ObservedTransport(**fields)


def repository_state(**overrides) -> LastVerifiedRepositoryState:
    fields = {
        "approved_remotes": ("https://github.com/company/repo",),
        "refs": (("refs/heads/main", "a"),),
        "index_tree_digest": "index",
        "worktree_security_digest": "worktree",
        "last_fetch_evidence_digest": "fetch",
        "verified_at": "2026-09-11T12:00:00Z",
    }
    fields.update(overrides)
    return LastVerifiedRepositoryState(**fields)


class RemoteValidationTests(unittest.TestCase):
    def test_matching_remote_is_allowed(self):
        verdict = validate_remote(approved_remote(), observed_identity(), SecurityClassification.CONFIDENTIAL)
        self.assertEqual("ALLOW", verdict.decision)

    def test_same_url_different_repository_identity_is_denied(self):
        verdict = validate_remote(approved_remote(), observed_identity(stable_repository_id="R_other"), SecurityClassification.CONFIDENTIAL)
        self.assertEqual("DENY", verdict.decision)

    def test_missing_stable_identity_for_sensitive_is_denied(self):
        self.assertEqual("DENY", validate_remote(approved_remote(), observed_identity(stable_repository_id=None), SecurityClassification.CONFIDENTIAL).decision)
        self.assertEqual("DENY", validate_remote(approved_remote(stable_repository_id=None), observed_identity(), SecurityClassification.CONFIDENTIAL).decision)

    def test_different_url_is_denied(self):
        observed = observed_identity(effective_fetch_url="https://github.com/company/other.git")
        self.assertEqual("DENY", validate_remote(approved_remote(), observed, SecurityClassification.CONFIDENTIAL).decision)

    def test_owner_mismatch_is_denied(self):
        self.assertEqual("DENY", validate_remote(approved_remote(), observed_identity(owner_org="attacker"), SecurityClassification.CONFIDENTIAL).decision)

    def test_visibility_mismatch_or_unknown_is_denied(self):
        self.assertEqual("DENY", validate_remote(approved_remote(), observed_identity(visibility=Visibility.PUBLIC), SecurityClassification.CONFIDENTIAL).decision)
        self.assertEqual("DENY", validate_remote(approved_remote(), observed_identity(visibility=None), SecurityClassification.CONFIDENTIAL).decision)

    def test_inline_credentials_are_denied(self):
        observed = observed_identity(effective_fetch_url="https://user:secret@github.com/company/repo.git")
        self.assertEqual("DENY", validate_remote(approved_remote(), observed, SecurityClassification.PERSONAL).decision)

    def test_provider_type_mismatch_is_denied(self):
        self.assertEqual("DENY", validate_remote(approved_remote(), observed_identity(provider_type="gitlab"), SecurityClassification.CONFIDENTIAL).decision)


class UrlNormalizationTests(unittest.TestCase):
    def test_equivalent_forms_normalize_identically(self):
        self.assertEqual(normalize_remote_url("ssh://git@github.com/company/repo"), normalize_remote_url("git@github.com:company/repo.git"))
        self.assertEqual("ssh://github.com/company/repo", normalize_remote_url("git@github.com:company/repo.git"))
        self.assertEqual("https://github.com/company/repo", normalize_remote_url("HTTPS://GitHub.com/company/repo/"))

    def test_invalid_or_unsupported_urls_normalize_to_none(self):
        self.assertIsNone(normalize_remote_url(""))
        self.assertIsNone(normalize_remote_url("github.com/company/repo"))
        self.assertEqual("file:///d:/repo", normalize_remote_url("file:///d:/repo.git/"))


class TransportValidationTests(unittest.TestCase):
    def test_matching_transport_is_allowed(self):
        self.assertEqual("ALLOW", validate_transport(transport_policy(), observed_transport()).decision)

    def test_protocol_not_in_allowlist_is_denied(self):
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(protocol="http")).decision)

    def test_ssh_command_override_is_denied(self):
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(ssh_command="ssh -oProxyCommand=evil")).decision)

    def test_proxy_override_is_denied(self):
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(proxy="http://proxy.example")).decision)

    def test_credential_helper_mismatch_is_denied(self):
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(credential_helper="osxkeychain")).decision)

    def test_transport_digest_mismatch_or_missing_is_denied(self):
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(effective_transport_config_digest="other")).decision)
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(effective_transport_config_digest=None)).decision)

    def test_transport_executable_mismatch_is_denied(self):
        self.assertEqual("DENY", validate_transport(transport_policy(), observed_transport(transport_executable_identity=None)).decision)


class RefPolicyTests(unittest.TestCase):
    def test_allowed_ref_patterns(self):
        approved = approved_remote(allowed_refs=("refs/heads/*", "refs/tags/v1.0"))
        self.assertTrue(ref_is_allowed(approved, "refs/heads/main"))
        self.assertTrue(ref_is_allowed(approved, "refs/tags/v1.0"))
        self.assertFalse(ref_is_allowed(approved, "refs/tags/v2.0"))
        self.assertFalse(ref_is_allowed(approved_remote(allowed_refs=()), "refs/heads/main"))


class FetchEvidenceTests(unittest.TestCase):
    def test_complete_evidence_requires_all_validations(self):
        result = build_fetch_evidence(
            approved_remote(), transport_policy(), observed_identity(), observed_transport(),
            ("refs/heads/main",), "2026-09-11T12:00:00Z", SecurityClassification.CONFIDENTIAL,
        )
        self.assertEqual("ALLOW", result.decision)
        self.assertIsInstance(result.evidence, FetchTransferEvidence)
        assert result.evidence is not None
        self.assertEqual("transport-digest", result.evidence.effective_transport_config_digest)

    def test_fetch_evidence_denies_on_remote_or_transport_failure(self):
        remote_failure = build_fetch_evidence(
            approved_remote(), transport_policy(), observed_identity(stable_repository_id="R_other"), observed_transport(),
            ("refs/heads/main",), "now", SecurityClassification.CONFIDENTIAL,
        )
        self.assertEqual("DENY", remote_failure.decision)
        self.assertIsNone(remote_failure.evidence)
        transport_failure = build_fetch_evidence(
            approved_remote(), transport_policy(), observed_identity(), observed_transport(proxy="http://proxy.example"),
            ("refs/heads/main",), "now", SecurityClassification.CONFIDENTIAL,
        )
        self.assertEqual("DENY", transport_failure.decision)

    def test_fetch_evidence_denies_unallowed_refs_and_empty_inputs(self):
        unallowed = build_fetch_evidence(
            approved_remote(), transport_policy(), observed_identity(), observed_transport(),
            ("refs/tags/v9",), "now", SecurityClassification.PERSONAL,
        )
        self.assertEqual("DENY", unallowed.decision)
        no_refs = build_fetch_evidence(
            approved_remote(), transport_policy(), observed_identity(), observed_transport(),
            (), "now", SecurityClassification.PERSONAL,
        )
        self.assertEqual("DENY", no_refs.decision)
        no_time = build_fetch_evidence(
            approved_remote(), transport_policy(), observed_identity(), observed_transport(),
            ("refs/heads/main",), "", SecurityClassification.PERSONAL,
        )
        self.assertEqual("DENY", no_time.decision)


class RepositoryStateTests(unittest.TestCase):
    def test_state_encoding_is_order_independent_and_roundtrips(self):
        first = repository_state(refs=(("refs/heads/main", "a"), ("refs/heads/dev", "b")))
        second = repository_state(refs=(("refs/heads/dev", "b"), ("refs/heads/main", "a")))
        self.assertEqual(first.encode(), second.encode())
        decoded = LastVerifiedRepositoryState.decode(first.encode())
        self.assertEqual(first.encode(), decoded.encode())

    def test_unsupported_state_schema_fails_closed(self):
        payload = json.dumps({
            "schema_version": 99,
            "approved_remotes": [],
            "refs": [],
            "index_tree_digest": "a",
            "worktree_security_digest": "b",
            "last_fetch_evidence_digest": "c",
            "verified_at": "d",
        })
        with self.assertRaises(ValueError):
            LastVerifiedRepositoryState.decode(payload)

    def test_state_comparison_reports_changes(self):
        recorded = repository_state()
        self.assertEqual((), compare_repository_state(recorded, repository_state()))
        self.assertEqual(("refs-changed",), compare_repository_state(recorded, repository_state(refs=(("refs/heads/main", "changed"),))))
        self.assertEqual(("remotes-changed",), compare_repository_state(recorded, repository_state(approved_remotes=("other",))))
        changed = repository_state(index_tree_digest="x", worktree_security_digest="y")
        self.assertEqual(("index-tree-changed", "worktree-changed"), compare_repository_state(recorded, changed))


class UnapprovedRemoteTests(unittest.TestCase):
    def test_only_unknown_remotes_are_reported(self):
        declared = {
            "origin": ("https://github.com/company/repo.git",),
            "upstream": ("https://github.com/fork/repo.git",),
        }
        self.assertEqual(("upstream",), unapproved_remotes(declared, (approved_remote(),)))

    def test_remote_with_one_unapproved_url_is_reported(self):
        declared = {"origin": ("https://github.com/company/repo.git", "https://evil.example/repo.git")}
        self.assertEqual(("origin",), unapproved_remotes(declared, (approved_remote(),)))