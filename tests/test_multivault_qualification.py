"""GUARDED qualification matrix (plan MV-21): cross-domain isolation end to end.

Each scenario exercises the real modules together for three domains
(Personal, Company A, Company B). The matrix proves fail-closed isolation;
it does not qualify any platform/harness/provider tuple (MV-00).
"""
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.admission import HarnessAutoloadAdapter, admit_repository
from ainative.multivault.audit import AuditLog, AuditRecord
from ainative.multivault.authority_store import AuthorityStore
from ainative.multivault.binding import WorkspaceDeclaration
from ainative.multivault.capability import ControlLevel, Observation, ObservationMode
from ainative.multivault.confinement import ResultConfinement
from ainative.multivault.mcp_adapter import McpOperation, ThinMcpAdapter
from ainative.multivault.persistence import StoreHeader, admit_load, namespace_for
from ainative.multivault.push_guard import DOMAIN_MISMATCH, GovernedPushAuthority
from ainative.multivault.resolver import resolve
from ainative.multivault.runtime_authority import (
    ImmutableAuthoritativeSecurityState,
    RuntimeAuthority,
    SensitiveQualification,
)
from ainative.multivault.schema import (
    AllowedContextEnvelope,
    MemoryPolicyDigest,
    PersistenceAssuranceDigest,
    SecurityClassification,
    SecurityDomain,
    SecurityEpoch,
)
from ainative.multivault.semantic import admit_semantic_session

DOMAINS = ("personal", "company-a", "company-b")
ROOT_A = str(Path(tempfile.gettempdir()) / "mv21-company-a")
ROOT_B = str(Path(tempfile.gettempdir()) / "mv21-company-b")


def authority_for(domain: str):
    state = ImmutableAuthoritativeSecurityState(
        security_domain_id=domain,
        security_epoch=SecurityEpoch(domain, "1", f"authority-{domain}"),
        vault_identity=f"vault-{domain}",
        checkout_identity=f"checkout-{domain}",
        project_security_id=f"project-{domain}",
        classification="CONFIDENTIAL",
        allowed_context_envelope=AllowedContextEnvelope((f"/srv/{domain}",), (f"/srv/{domain}",)),
        approved_model_egress_digest="egress",
        memory_policy_digest="memory",
        persistence_assurance_digest="persistence",
        execution_profile="GUARDED",
        runtime_observation_policy_digest="observation",
        authority_instance_id=f"authority-{domain}",
    )
    authority = RuntimeAuthority(state)
    handle = authority.issue_phase_b_handle(f"launcher-{domain}", SensitiveQualification(True, True, True))
    return authority, handle


def namespace_for_domain(domain: str):
    return namespace_for(
        SecurityDomain(domain, f"vault-{domain}", f"project-{domain}", f"operator-{domain}"),
        AllowedContextEnvelope((f"/srv/{domain}",), (f"/srv/{domain}",)),
        MemoryPolicyDigest({"scope": "domain"}),
        PersistenceAssuranceDigest("GUARDED", "local", "local"),
    )


class GuardedQualificationMatrix(unittest.TestCase):
    def test_memory_namespaces_never_load_across_domains(self):
        namespaces = {domain: namespace_for_domain(domain) for domain in DOMAINS}
        self.assertEqual(3, len({namespace.namespace_digest for namespace in namespaces.values()}))
        header = StoreHeader(1, namespaces["personal"].namespace_digest)
        for domain in ("company-a", "company-b"):
            self.assertEqual("REFUSE", admit_load(header, namespaces[domain]).decision)

    def test_repository_declarations_cannot_expand_or_cross_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AuthorityStore(Path(directory) / "authority.json")
            store.replace({"company-a": {"vault": "vault-company-a", "checkout": "checkout-company-a", "classification": "PERSONAL"}})
            allowed = resolve(WorkspaceDeclaration("company-a", "vault-company-a", "checkout-company-a", SecurityClassification.PERSONAL), store)
            self.assertTrue(allowed.authorized)
            expanded = resolve(WorkspaceDeclaration("company-a", "vault-company-a", "checkout-company-a", SecurityClassification.CRITICAL), store)
            self.assertFalse(expanded.authorized)
            foreign = resolve(WorkspaceDeclaration("personal", "vault-personal", "checkout-personal", SecurityClassification.PERSONAL), store)
            self.assertFalse(foreign.authorized)

    def test_mcp_sessions_reject_foreign_callers_and_cross_domain_handles(self):
        authority_a, handle_a = authority_for("company-a")
        _, handle_b = authority_for("company-b")
        confinement = ResultConfinement("project-company-a", (ROOT_A,), lambda path: True)
        adapter = ThinMcpAdapter(
            launcher_identity="launcher-company-a",
            security_domain_id="company-a",
            authority=authority_a,
            handle=handle_a,
            confinement=confinement,
        )
        ok = adapter.request(capability=adapter.session_capability(), caller_identity="launcher-company-a", operation=McpOperation.VAULT_READ, result_paths=(ROOT_A + "/note.md",))
        self.assertEqual("ALLOW", ok.decision)
        foreign_caller = adapter.request(capability=adapter.session_capability(), caller_identity="intruder", operation=McpOperation.VAULT_READ)
        self.assertEqual("DENY", foreign_caller.decision)
        cross_domain = ThinMcpAdapter(
            launcher_identity="launcher-company-a",
            security_domain_id="company-a",
            authority=authority_a,
            handle=handle_b,
            confinement=confinement,
        )
        self.assertEqual("DENY", cross_domain.request(capability=cross_domain.session_capability(), caller_identity="launcher-company-a", operation=McpOperation.VAULT_READ).decision)
        escape = adapter.request(capability=adapter.session_capability(), caller_identity="launcher-company-a", operation=McpOperation.VAULT_READ, result_paths=(ROOT_B + "/secret.md",))
        self.assertEqual("DENY", escape.decision)

    def test_push_capabilities_never_cross_domains_and_never_replay(self):
        authority_a = GovernedPushAuthority("company-a", "checkout-company-a")
        authority_b = GovernedPushAuthority("company-b", "checkout-company-b")
        capability = authority_a.issue(intent_stub())
        wrong_domain = authority_b.authorize(capability, "refs/heads/main aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/heads/main bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n")
        self.assertEqual(DOMAIN_MISMATCH, wrong_domain.code)
        first = authority_a.authorize(capability, "refs/heads/main aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/heads/main bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n")
        self.assertEqual("ALLOW", first.decision)
        self.assertEqual("DENY", authority_a.authorize(capability, "refs/heads/main aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/heads/main bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n").decision)

    def test_repository_and_semantic_admission_deny_without_probe_evidence(self):
        surfaces = ()
        unknown_adapter = HarnessAutoloadAdapter(
            harness="opencode", harness_version="1", adapter_version="1", probe_version="1",
            disable_control=ControlLevel.PARTIAL, observation=Observation(ObservationMode.EVENT), evidence_digest="evidence",
        )
        self.assertEqual("DENY", admit_repository(surfaces, unknown_adapter, SecurityClassification.CONFIDENTIAL).decision)
        self.assertEqual("DENY", admit_semantic_session(None, SecurityClassification.CONFIDENTIAL).decision)

    def test_launcher_loss_revokes_all_handles(self):
        authority, handle = authority_for("company-a")
        adapter = ThinMcpAdapter(
            launcher_identity="launcher-company-a",
            security_domain_id="company-a",
            authority=authority,
            handle=handle,
            confinement=ResultConfinement("project-company-a", (ROOT_A,), lambda path: True),
        )
        authority.revoke_all("LAUNCHER_LOST")
        outcome = adapter.request(capability=adapter.session_capability(), caller_identity="launcher-company-a", operation=McpOperation.VAULT_READ)
        self.assertEqual("DENY", outcome.decision)

    def test_matrix_decisions_are_auditable_without_content(self):
        with tempfile.TemporaryDirectory() as directory:
            log = AuditLog(Path(directory) / "audit.jsonl")
            for domain in DOMAINS:
                log.append(AuditRecord(
                    timestamp="2026-09-11T12:00:00Z",
                    security_domain_id=domain,
                    operation="qualification.matrix",
                    decision="DENY",
                    reason_code="AINATIVE_CROSS_DOMAIN_DENIED",
                    qualification_level="GUARDED",
                ))
            self.assertEqual(3, len(log.query(decision="DENY")))
            self.assertEqual(1, len(log.query(security_domain_id="company-a")))


def intent_stub():
    from ainative.multivault.git_authority import ApprovedGitRemote, GitTransportPolicy, Visibility
    from ainative.multivault.push_guard import PushIntent

    return PushIntent(
        source_oid="a" * 40,
        expected_remote_base_oid="b" * 40,
        target_ref="refs/heads/main",
        exact_refspec="refs/heads/main:refs/heads/main",
        approved_remote=ApprovedGitRemote(
            canonical_fetch_url="https://github.com/company/repo.git",
            canonical_push_url="https://github.com/company/repo.git",
            provider_type="github",
            stable_repository_id="R_kgDOAAAAAA",
            required_owner_org="company",
            required_visibility_for_push=Visibility.PRIVATE,
            allowed_refs=("refs/heads/*",),
        ),
        transport_policy=GitTransportPolicy(
            protocol_allowlist=("https",),
            transport_executable_identity="git",
            proxy=None,
            ssh_command=None,
            credential_helper=None,
            ssh_peer_policy="pinned",
            tls_peer_policy="verified",
            effective_transport_config_digest="digest",
        ),
        candidate_object_set_digest="candidates",
        scan_result_digest="scan",
        expected_git_identity="Rwanbt <barat.erwan@gmail.com>",
    )