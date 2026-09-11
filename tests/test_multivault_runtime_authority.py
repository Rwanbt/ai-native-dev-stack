import unittest

from ainative.multivault.runtime_authority import (
    ImmutableAuthoritativeSecurityState,
    RuntimeAuthority,
    RuntimeContextHandle,
    SensitiveQualification,
)
from ainative.multivault.schema import AllowedContextEnvelope, SecurityEpoch


def authority() -> RuntimeAuthority:
    state = ImmutableAuthoritativeSecurityState(
        security_domain_id="company-a",
        security_epoch=SecurityEpoch("company-a", "1", "authority-1"),
        vault_identity="vault-a",
        checkout_identity="checkout-a",
        project_security_id="project-a",
        classification="CONFIDENTIAL",
        allowed_context_envelope=AllowedContextEnvelope(("repo-a",), ("vault-a",)),
        approved_model_egress_digest="egress",
        memory_policy_digest="memory",
        persistence_assurance_digest="persistence",
        execution_profile="GUARDED",
        runtime_observation_policy_digest="observation",
        authority_instance_id="authority-1",
    )
    return RuntimeAuthority(state)


class RuntimeAuthorityTests(unittest.TestCase):
    def test_missing_phase_b_proof_never_issues_a_handle(self):
        self.assertIsNone(authority().issue_phase_b_handle("launcher-a", SensitiveQualification()))

    def test_handle_is_opaque_and_bound_to_its_caller(self):
        runtime_authority = authority()
        handle = runtime_authority.issue_phase_b_handle(
            "launcher-a", SensitiveQualification(True, True, True)
        )
        self.assertIsNotNone(handle)
        assert handle is not None
        self.assertNotIn(handle._secret, repr(handle))
        self.assertEqual("<redacted>", str(handle))
        self.assertIsNotNone(runtime_authority.resolve(handle, "launcher-a"))
        self.assertIsNone(runtime_authority.resolve(handle, "foreign-launcher"))

    def test_revoke_all_invalidates_all_issued_handles(self):
        runtime_authority = authority()
        handle = runtime_authority.issue_phase_b_handle(
            "launcher-a", SensitiveQualification(True, True, True)
        )
        assert handle is not None
        runtime_authority.revoke_all("LAUNCHER_LOST")
        self.assertIsNone(runtime_authority.resolve(handle, "launcher-a"))

    def test_forged_handle_does_not_resolve(self):
        runtime_authority = authority()
        forged = RuntimeContextHandle(
            "authority-1", "company-a", runtime_authority.state.security_epoch.digest(), "not-issued"
        )
        self.assertIsNone(runtime_authority.resolve(forged, "launcher-a"))
