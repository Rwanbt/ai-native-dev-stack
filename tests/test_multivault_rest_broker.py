import unittest

from ainative.multivault.rest_broker import (
    DomainRestBroker,
    EndpointCorrelation,
    RestCredential,
    RestEndpoint,
)
from ainative.multivault.runtime_authority import (
    ImmutableAuthoritativeSecurityState,
    RuntimeAuthority,
    SensitiveQualification,
)
from ainative.multivault.schema import AllowedContextEnvelope, SecurityEpoch


def authority() -> RuntimeAuthority:
    return RuntimeAuthority(
        ImmutableAuthoritativeSecurityState(
            "company-a", SecurityEpoch("company-a", "1", "authority-1"), "vault-a",
            "checkout-a", "project-a", "CONFIDENTIAL",
            AllowedContextEnvelope(("repo-a",), ("vault-a",)), "egress", "memory",
            "persistence", "GUARDED", "observation", "authority-1",
        )
    )


def broker() -> DomainRestBroker:
    correlation = EndpointCorrelation(
        "company-a", "vault-a", RestEndpoint("https://127.0.0.1:27124/"), "probe-digest", True
    )
    return DomainRestBroker(correlation, RestCredential("secret"))


class RestBrokerTests(unittest.TestCase):
    def test_only_a_live_domain_bound_handle_releases_scoped_credential(self):
        runtime_authority = authority()
        handle = runtime_authority.issue_phase_b_handle("launcher-a", SensitiveQualification(True, True, True))
        assert handle is not None
        credential = broker().authorize(
            runtime_authority, handle, "launcher-a", RestEndpoint("https://127.0.0.1:27124/")
        )
        self.assertIsNotNone(credential)
        assert credential is not None
        self.assertNotIn("secret", repr(credential))
        self.assertIsNone(broker().authorize(runtime_authority, handle, "foreign", RestEndpoint("https://127.0.0.1:27124/")))

    def test_uncorrelated_or_non_literal_loopback_endpoint_is_denied(self):
        runtime_authority = authority()
        handle = runtime_authority.issue_phase_b_handle("launcher-a", SensitiveQualification(True, True, True))
        assert handle is not None
        for endpoint in (
            RestEndpoint("https://localhost:27124/"),
            RestEndpoint("https://example.test:27124/"),
            RestEndpoint("https://127.0.0.1:not-a-port/"),
            RestEndpoint("https://[malformed"),
        ):
            self.assertIsNone(broker().authorize(runtime_authority, handle, "launcher-a", endpoint))

    def test_revoked_handle_cannot_reacquire_a_rest_credential(self):
        runtime_authority = authority()
        handle = runtime_authority.issue_phase_b_handle("launcher-a", SensitiveQualification(True, True, True))
        assert handle is not None
        runtime_authority.revoke(handle, "DRIFT")
        self.assertIsNone(broker().authorize(runtime_authority, handle, "launcher-a", RestEndpoint("https://127.0.0.1:27124/")))
