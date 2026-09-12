"""Sync composition E2E: denials never construct an engine; transfers only via the engine."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.git_authority import (
    ApprovedGitRemote,
    GitTransportPolicy,
    ObservedRepositoryIdentity,
    ObservedTransport,
    Visibility,
)
from ainative.multivault.identity import (
    checkout_identity_digest,
    discover_checkout,
    discover_vault,
    vault_root_identity,
)
from ainative.multivault.sync_composition import SyncRequest, compose_fetch, compose_push


class SyncCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.vault = base / "vault-a"
        self.vault.mkdir()
        self.other_vault = base / "vault-b"
        self.other_vault.mkdir()
        self.checkout = self.git_repository("checkout-a")
        self.copied_checkout = self.git_repository("checkout-copy")
        self.store = AuthorityStore(base / "authority.json")
        self.binding = {
            "vault": "vault-a",
            "checkout": "checkout-a",
            "classification": "PERSONAL",
            "roots": [],
            "root_identity": vault_root_identity(discover_vault("vault-a", self.vault)),
            "checkout_identity": checkout_identity_digest(discover_checkout(self.checkout)),
        }
        self.store.replace({"company-a": dict(self.binding)})
        self.origin = base / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.origin)], check=True)
        self.repo, self.url = self.repository_with_origin()

    def tearDown(self):
        self.temp.cleanup()

    def git_repository(self, name):
        root = Path(self.temp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        return root

    def repository_with_origin(self):
        repo = Path(self.temp.name) / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-q", "-m", "init"], check=True)
        url = self.origin.as_uri()
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)
        subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:refs/heads/main"], check=True)
        return repo, url

    def request(self, **overrides):
        values = dict(
            store_path=self.store.path,
            domain="company-a",
            vault_logical_id="vault-a",
            checkout_identity="checkout-a",
            vault_root=self.vault,
            checkout_root=self.checkout,
            repository=self.repo,
        )
        values.update(overrides)
        return SyncRequest(**values)

    def approved(self, url=None):
        url = url or self.url
        return ApprovedGitRemote(
            canonical_fetch_url=url,
            canonical_push_url=url,
            provider_type="local",
            stable_repository_id=None,
            required_owner_org="local-team",
            required_visibility_for_push=Visibility.PRIVATE,
            allowed_refs=("refs/heads/*",),
            require_stable_repository_id=False,
        )

    def policy(self):
        return GitTransportPolicy(
            protocol_allowlist=("file",),
            transport_executable_identity="git-local",
            proxy=None,
            ssh_command=None,
            credential_helper=None,
            ssh_peer_policy="pinned",
            tls_peer_policy="pinned",
            effective_transport_config_digest="digest-1",
        )

    def observed_remote(self, url=None, **overrides):
        values = dict(
            provider_type="local",
            stable_repository_id=None,
            owner_org="local-team",
            visibility=Visibility.PRIVATE,
            effective_fetch_url=url or self.url,
            effective_push_url=url or self.url,
        )
        values.update(overrides)
        return ObservedRepositoryIdentity(**values)

    def observed_transport(self, **overrides):
        values = dict(
            protocol="file",
            transport_executable_identity="git-local",
            proxy=None,
            ssh_command=None,
            credential_helper=None,
            effective_transport_config_digest="digest-1",
        )
        values.update(overrides)
        return ObservedTransport(**values)

    def fetch(self, request=None, **overrides):
        arguments = dict(
            approved_remote=self.approved(),
            transport_policy=self.policy(),
            observed_remote=self.observed_remote(),
            observed_transport=self.observed_transport(),
            requested_refs=("refs/heads/main",),
            verified_at="2026-09-12T00:00:00Z",
        )
        arguments.update(overrides)
        return compose_fetch(request or self.request(), **arguments)

    def assert_no_engine_and_denied(self, outcome, code, **request_overrides):
        with mock.patch("ainative.multivault.sync_composition.GovernedTransferEngine") as engine_class:
            outcome = self.fetch(request=self.request(**request_overrides))
            self.assertEqual(0, engine_class.call_count)
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual(code, outcome.code)

    def test_wrong_domain_denies_before_any_engine(self):
        self.assert_no_engine_and_denied(None, "DENY_DECLARATION_NOT_ADMITTED", domain="company-b")

    def test_missing_binding_denies_before_any_engine(self):
        empty = Path(self.temp.name) / "empty-authority.json"
        self.assert_no_engine_and_denied(None, "DENY_DECLARATION_NOT_ADMITTED", store_path=empty)

    def test_stale_vault_denies_before_any_engine(self):
        self.assert_no_engine_and_denied(None, "DENY_ROOT_STALE", vault_root=self.other_vault)

    def test_stale_checkout_denies_before_any_engine(self):
        self.assert_no_engine_and_denied(None, "DENY_CHECKOUT_STALE", checkout_root=self.copied_checkout)

    def test_legacy_binding_denies_before_any_engine(self):
        legacy = {key: value for key, value in self.binding.items() if key != "checkout_identity"}
        self.store.replace({"company-a": legacy})
        outcome = self.fetch()
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual("DENY_CHECKOUT_IDENTITY_UNRECORDED", outcome.code)

    def test_mismatched_observed_remote_is_denied_by_the_engine(self):
        outcome = self.fetch(observed_remote=self.observed_remote(url="file:///C:/other/repo"))
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual("AINATIVE_FETCH_DESTINATION_DENIED", outcome.code)

    def test_force_refspec_is_denied_by_the_engine_before_network(self):
        outcome = compose_push(
            self.request(),
            approved_remote=self.approved(),
            transport_policy=self.policy(),
            observed_remote=self.observed_remote(),
            observed_transport=self.observed_transport(),
            source_oid="a" * 40,
            expected_remote_base_oid="b" * 40,
            target_ref="refs/heads/main",
            exact_refspec="+refs/heads/main:refs/heads/main",
            expected_git_identity="example.invalid",
        )
        self.assertEqual("DENY", outcome.decision)
        self.assertEqual("AINATIVE_FORCE_PUSH_DENIED", outcome.code)

    def test_nominal_fetch_succeeds_through_the_governed_engine(self):
        outcome = self.fetch()
        self.assertEqual("ALLOW", outcome.decision)
        self.assertEqual("OK", outcome.code)
        self.assertIsNotNone(outcome.evidence)
        self.assertIsNotNone(outcome.repository_state)


class SyncCompositionStructureTests(unittest.TestCase):
    def test_composition_module_constructs_no_authoritative_object_or_decision(self):
        source = (Path(__file__).resolve().parent.parent / "ainative" / "multivault" / "sync_composition.py").read_text(encoding="utf-8")
        forbidden = (
            "AllowedContextEnvelope(",
            "RuntimeContextHandle(",
            "SensitiveQualification(",
            "GovernedPushCapability(",
            "SecurityClassification.CONFIDENTIAL",
            "SecurityClassification.CRITICAL",
            "classification >=",
            "classification >",
            "subprocess",
        )
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
