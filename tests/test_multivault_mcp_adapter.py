import tempfile
import time
import unittest
from pathlib import Path

from ainative.multivault.confinement import ResultConfinement
from ainative.multivault.mcp_adapter import (
    McpOperation,
    SessionCapability,
    ThinMcpAdapter,
)
from ainative.multivault.runtime_authority import (
    ImmutableAuthoritativeSecurityState,
    RuntimeAuthority,
    SensitiveQualification,
)
from ainative.multivault.schema import AllowedContextEnvelope, SecurityEpoch

ROOT = Path(tempfile.gettempdir()) / "mv15-repo-a"
OUTSIDE = Path(tempfile.gettempdir()) / "mv15-repo-b"


def make_authority(domain: str = "company-a"):
    state = ImmutableAuthoritativeSecurityState(
        security_domain_id=domain,
        security_epoch=SecurityEpoch(domain, "1", "authority-1"),
        vault_identity=f"vault-{domain}",
        checkout_identity=f"checkout-{domain}",
        project_security_id="project-a",
        classification="CONFIDENTIAL",
        allowed_context_envelope=AllowedContextEnvelope((str(ROOT),), (str(ROOT),)),
        approved_model_egress_digest="egress",
        memory_policy_digest="memory",
        persistence_assurance_digest="persistence",
        execution_profile="GUARDED",
        runtime_observation_policy_digest="observation",
        authority_instance_id="authority-1",
    )
    authority = RuntimeAuthority(state)
    return authority, authority.issue_phase_b_handle("launcher-a", SensitiveQualification(True, True, True))


def build(
    domain: str = "company-a",
    authority=None,
    handle=None,
    clock=None,
    allow_writes: bool = True,
    vault_confine=None,
) -> ThinMcpAdapter:
    if authority is None or handle is None:
        authority, handle = make_authority(domain)
    confinement = ResultConfinement("project-a", (str(ROOT),), vault_confine if vault_confine is not None else (lambda path: True))
    return ThinMcpAdapter(
        launcher_identity="launcher-a",
        security_domain_id=domain,
        authority=authority,
        handle=handle,
        confinement=confinement,
        allowed_write_targets=(str(ROOT),) if allow_writes else (),
        ttl_seconds=60,
        clock=clock if clock is not None else time.monotonic,
    )


def request(adapter, operation, result_paths=(), capability=None, caller="launcher-a"):
    return adapter.request(
        capability=capability if capability is not None else adapter.session_capability(),
        caller_identity=caller,
        operation=operation,
        result_paths=result_paths,
    )


class ThinMcpAdapterTests(unittest.TestCase):
    def test_valid_read_is_revalidated_and_allowed(self):
        self.assertEqual("ALLOW", request(build(), McpOperation.VAULT_READ, (str(ROOT / "note.md"),)).decision)

    def test_empty_result_set_is_allowed(self):
        self.assertEqual("ALLOW", request(build(), McpOperation.VAULT_SEARCH, ()).decision)

    def test_foreign_capability_is_denied(self):
        adapter = build()
        response = request(adapter, McpOperation.VAULT_READ, (str(ROOT / "note.md"),), capability=SessionCapability("forged"))
        self.assertEqual("DENY", response.decision)

    def test_foreign_caller_is_denied(self):
        response = request(build(), McpOperation.VAULT_READ, (str(ROOT / "note.md"),), caller="intruder")
        self.assertEqual("DENY", response.decision)

    def test_expired_session_is_denied(self):
        now = [0.0]
        adapter = build(clock=lambda: now[0])
        now[0] = 120.0
        self.assertEqual("DENY", request(adapter, McpOperation.VAULT_READ, (str(ROOT / "note.md"),)).decision)

    def test_closed_session_is_denied(self):
        adapter = build()
        adapter.close()
        self.assertEqual("DENY", request(adapter, McpOperation.VAULT_READ, (str(ROOT / "note.md"),)).decision)

    def test_cross_domain_handle_is_denied(self):
        other_authority, other_handle = make_authority("company-b")
        adapter = build(domain="company-a", authority=other_authority, handle=other_handle)
        self.assertEqual("DENY", request(adapter, McpOperation.VAULT_READ, ()).decision)

    def test_response_path_escape_is_denied(self):
        self.assertEqual("DENY", request(build(), McpOperation.VAULT_READ, (str(OUTSIDE / "secret.md"),)).decision)

    def test_write_outside_allowed_targets_is_denied(self):
        self.assertEqual("DENY", request(build(), McpOperation.VAULT_WRITE, (str(OUTSIDE / "x.md"),)).decision)

    def test_write_without_allowed_targets_is_denied(self):
        self.assertEqual("DENY", request(build(allow_writes=False), McpOperation.VAULT_WRITE, (str(ROOT / "x.md"),)).decision)

    def test_write_inside_allowed_targets_is_allowed(self):
        self.assertEqual("ALLOW", request(build(), McpOperation.VAULT_WRITE, (str(ROOT / "x.md"),)).decision)

    def test_write_denied_by_vault_protocol_confinement(self):
        adapter = build(vault_confine=lambda path: False)
        self.assertEqual("DENY", request(adapter, McpOperation.VAULT_WRITE, (str(ROOT / "x.md"),)).decision)

    def test_unknown_operation_is_denied(self):
        adapter = build()
        response = adapter.request(
            capability=adapter.session_capability(),
            caller_identity="launcher-a",
            operation="vault.read",
            result_paths=(),
        )
        self.assertEqual("DENY", response.decision)

    def test_endpoint_ids_are_unique_per_session(self):
        self.assertNotEqual(build().endpoint_id, build().endpoint_id)

    def test_session_capability_representations_are_redacted(self):
        capability = build().session_capability()
        self.assertEqual("<redacted>", str(capability))
        self.assertNotIn(capability._value, repr(capability))