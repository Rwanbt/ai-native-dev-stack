import time
import unittest
from dataclasses import replace

from ainative.multivault.git_authority import ApprovedGitRemote, GitTransportPolicy, Visibility
from ainative.multivault.push_guard import (
    CAPABILITY_EXPIRED,
    CAPABILITY_MISMATCH,
    CAPABILITY_REPLAYED,
    CHECKOUT_MISMATCH,
    DIRECT_PUSH_DENIED,
    DOMAIN_MISMATCH,
    REFS_MISMATCH,
    GovernedPushAuthority,
    GovernedPushCapability,
    PushIntent,
    parse_pre_push_lines,
)

SOURCE = "a" * 40
BASE = "b" * 40


def approved_remote() -> ApprovedGitRemote:
    return ApprovedGitRemote(
        canonical_fetch_url="https://github.com/company/repo.git",
        canonical_push_url="git@github.com:company/repo.git",
        provider_type="github",
        stable_repository_id="R_kgDOAAAAAA",
        required_owner_org="company",
        required_visibility_for_push=Visibility.PRIVATE,
        allowed_refs=("refs/heads/*",),
    )


def transport_policy() -> GitTransportPolicy:
    return GitTransportPolicy(
        protocol_allowlist=("ssh",),
        transport_executable_identity="git-2.51.1",
        proxy=None,
        ssh_command=None,
        credential_helper="store",
        ssh_peer_policy="pinned",
        tls_peer_policy="verified",
        effective_transport_config_digest="transport-digest",
    )


def intent(**overrides) -> PushIntent:
    fields = {
        "source_oid": SOURCE,
        "expected_remote_base_oid": BASE,
        "target_ref": "refs/heads/main",
        "exact_refspec": "refs/heads/main:refs/heads/main",
        "approved_remote": approved_remote(),
        "transport_policy": transport_policy(),
        "candidate_object_set_digest": "candidates",
        "scan_result_digest": "scan",
        "expected_git_identity": "Rwanbt <barat.erwan@gmail.com>",
    }
    fields.update(overrides)
    return PushIntent(**fields)


def stdin_line(**overrides) -> str:
    fields = {
        "local_ref": "refs/heads/main",
        "local_oid": SOURCE,
        "remote_ref": "refs/heads/main",
        "remote_oid": BASE,
    }
    fields.update(overrides)
    return f"{fields['local_ref']} {fields['local_oid']} {fields['remote_ref']} {fields['remote_oid']}\n"


class PushGuardTests(unittest.TestCase):
    def authority(self, clock=None) -> GovernedPushAuthority:
        if clock is None:
            return GovernedPushAuthority("company-a", "checkout-a")
        return GovernedPushAuthority("company-a", "checkout-a", clock=clock)

    def test_governed_push_is_authorized_once(self):
        authority = self.authority()
        capability = authority.issue(intent())
        result = authority.authorize(capability, stdin_line())
        self.assertEqual("ALLOW", result.decision)
        self.assertEqual("OK", result.code)

    def test_second_authorization_is_a_replay_denial(self):
        authority = self.authority()
        capability = authority.issue(intent())
        self.assertEqual("ALLOW", authority.authorize(capability, stdin_line()).decision)
        replay = authority.authorize(capability, stdin_line())
        self.assertEqual("DENY", replay.decision)
        self.assertEqual(CAPABILITY_REPLAYED, replay.code)

    def test_forged_marker_or_absent_capability_is_direct_push_denied(self):
        authority = self.authority()
        for forged in (None, "GOVERNED_PUSH=1", "not-a-capability"):
            result = authority.authorize(forged, stdin_line())
            self.assertEqual("DENY", result.decision)
            self.assertEqual(DIRECT_PUSH_DENIED, result.code)

    def test_expired_capability_is_denied(self):
        now = [0.0]
        authority = self.authority(clock=lambda: now[0])
        capability = authority.issue(intent())
        now[0] = 1000.0
        result = authority.authorize(capability, stdin_line())
        self.assertEqual("DENY", result.decision)
        self.assertEqual(CAPABILITY_EXPIRED, result.code)

    def test_wrong_domain_or_checkout_is_denied(self):
        capability = self.authority().issue(intent())
        wrong_domain = GovernedPushAuthority("company-b", "checkout-a").authorize(capability, stdin_line())
        self.assertEqual(DOMAIN_MISMATCH, wrong_domain.code)
        wrong_checkout = GovernedPushAuthority("company-a", "checkout-b").authorize(capability, stdin_line())
        self.assertEqual(CHECKOUT_MISMATCH, wrong_checkout.code)

    def test_ref_mismatches_are_denied(self):
        cases = (
            stdin_line(local_oid="c" * 40),
            stdin_line(remote_ref="refs/heads/other"),
            stdin_line(remote_oid="d" * 40),
            stdin_line(local_ref="refs/heads/other"),
        )
        for line in cases:
            authority = self.authority()
            capability = authority.issue(intent())
            result = authority.authorize(capability, line)
            self.assertEqual("DENY", result.decision)
            self.assertEqual(REFS_MISMATCH, result.code)

    def test_one_invalid_ref_among_many_rejects_the_whole_transaction(self):
        authority = self.authority()
        capability = authority.issue(intent())
        stdin = stdin_line() + stdin_line(remote_ref="refs/heads/evil", remote_oid="e" * 40)
        result = authority.authorize(capability, stdin)
        self.assertEqual("DENY", result.decision)
        self.assertEqual(REFS_MISMATCH, result.code)

    def test_empty_or_malformed_input_is_denied(self):
        authority = self.authority()
        capability = authority.issue(intent())
        for stdin in ("", "one two three\n"):
            result = authority.authorize(capability, stdin)
            self.assertEqual("DENY", result.decision)
            self.assertEqual(REFS_MISMATCH, result.code)

    def test_failed_attempt_does_not_consume_the_capability(self):
        authority = self.authority()
        capability = authority.issue(intent())
        self.assertEqual("DENY", authority.authorize(capability, stdin_line(remote_ref="refs/heads/other")).decision)
        self.assertEqual("ALLOW", authority.authorize(capability, stdin_line()).decision)

    def test_capability_is_redacted_and_nonces_are_unique(self):
        authority = self.authority()
        capability = authority.issue(intent())
        self.assertEqual("<redacted>", str(capability))
        self.assertNotIn(capability._nonce, repr(capability))
        self.assertNotEqual(capability._nonce, authority.issue(intent())._nonce)

    def test_intent_digest_is_stable_and_binds_the_transfer(self):
        self.assertEqual(intent().digest(), intent().digest())
        self.assertNotEqual(intent().digest(), intent(target_ref="refs/heads/other").digest())
        self.assertNotEqual(intent().digest(), intent(scan_result_digest="other").digest())

    def test_capability_cannot_be_rebound_to_another_source(self):
        authority = self.authority()
        capability = authority.issue(intent())
        forged = replace(capability, source_oid="f" * 40)
        result = authority.authorize(forged, stdin_line(local_oid="f" * 40))
        self.assertEqual("DENY", result.decision)
        self.assertEqual(CAPABILITY_MISMATCH, result.code)

    def test_parse_pre_push_lines(self):
        self.assertEqual(1, len(parse_pre_push_lines(stdin_line() + "\n")))
        with self.assertRaises(ValueError):
            parse_pre_push_lines("one two three\n")