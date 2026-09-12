"""Canonical, descriptive Multi-Vault identities and digests for MV-02.

See ADR-0013 sections 1-8. The eight digest types below are canonical
containers for their normative "canonical input" field lists (ADR-0013
section 7). MV-02 owns the shape and the canonicalization contract; the
runtime logic that populates a digest with real measured evidence belongs
to the MV item that owns that evidence (MV-14 semantic drift, MV-17..19 Git
transfer, MV-22/23 boundary qualification).
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum, IntEnum
from hashlib import sha256
import json
from typing import Any

SCHEMA_VERSION = 1


def canonical_json(value: Any) -> bytes:
    """Stable JSON encoding: sorted keys, compact separators, no host repr()."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()


class SecurityClassification(IntEnum):
    """ADR-0013 section 1. Ordered so `requested > allowed` means the request
    expands classification -- the comparison MV-06's admission check needs."""
    PERSONAL = 0
    TEAM = 1
    CONFIDENTIAL = 2
    CRITICAL = 3


class ProviderClass(str, Enum):
    """ADR-0014 section 3. Every provider adapter declares exactly one of these."""
    CLOUD_API = "cloud_api"
    ONPREM_MANAGED = "onprem_managed"
    LOCAL_RUNTIME = "local_runtime"


@dataclass(frozen=True)
class SecurityDomain:
    """ADR-0013 section 7.1 -- SecurityDomainIdentity. Excludes mutable runtime data."""
    security_domain_id: str
    vault_logical_id: str
    project_security_id: str
    operator_authority_domain_id: str

    def identity_digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})


@dataclass(frozen=True)
class SecurityEpoch:
    """ADR-0013 section 7.2. Advancing this revokes previously issued handles."""
    security_domain_id: str
    epoch_counter_or_nonce: str
    authority_instance_generation: str

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})


@dataclass(frozen=True)
class AllowedContextEnvelope:
    """ADR-0013 section 5. The authoritative maximum set of context sources
    that may be considered for a session."""
    repository_roots: tuple[str, ...]
    vault_memory_roots: tuple[str, ...]
    shared_memory_roots: tuple[str, ...] = ()
    semantic_roots: tuple[str, ...] = ()
    graph_roots: tuple[str, ...] = ()
    allowed_write_targets: tuple[str, ...] = ()
    project_boundaries: tuple[str, ...] = ()
    source_classes: tuple[str, ...] = ()

    def exposure_digest(self) -> str:
        """ADR-0013 section 7.3 -- ContextExposureDigest."""
        normalized = {key: sorted(value) for key, value in asdict(self).items()}
        return digest({"schema_version": SCHEMA_VERSION, "envelope": normalized})


@dataclass(frozen=True)
class MemoryPolicyDigest:
    """ADR-0013 section 7.4. Hashes the full normalized memory-policy object,
    never a hand-maintained subset of selected fields."""
    policy: dict[str, Any]

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, "policy": self.policy})


@dataclass(frozen=True)
class PersistenceAssuranceDigest:
    """ADR-0013 section 7.5. V1 compatibility is exact-match only."""
    effective_execution_profile: str
    provider_egress_class: str
    storage_assurance_class: str

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})


@dataclass(frozen=True)
class SemanticEgressDigest:
    """ADR-0013 section 7.6. `fields` carries the versioned semantic-config
    schema MV-14 defines; MV-02 only fixes the canonicalization contract."""
    fields: dict[str, Any]

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, "semantic_egress": self.fields})


@dataclass(frozen=True)
class ExecutionBoundaryDigest:
    """ADR-0013 section 7.7. Binds ENFORCED-* qualification to measured
    boundary evidence; MV-22/23 populate these fields with real evidence."""
    network_policy: str
    mounts: str
    filesystem_acl_boundary: str
    credential_boundary: str
    harness_config_roots: tuple[str, ...]
    runtime_identity: str
    ipc_topology: str
    rest_reachability: str
    authority_store_placement: str
    provider_route_policy: str
    git_transfer_boundary: str
    process_containment: str

    def digest(self) -> str:
        normalized = {**asdict(self), "harness_config_roots": sorted(self.harness_config_roots)}
        return digest({"schema_version": SCHEMA_VERSION, **normalized})


@dataclass(frozen=True)
class PushIntentDigest:
    """ADR-0013 section 7.8 / ADR-0016 section 16. Binds one governed Git
    push authorization to its exact transfer intent."""
    source_oid: str
    expected_remote_base_oid: str
    target_ref: str
    exact_refspec: str
    approved_git_remote_digest: str
    git_transport_policy_digest: str
    candidate_object_set_digest: str
    scan_result_digest: str
    expected_git_identity: str

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})


@dataclass(frozen=True)
class ApprovedModelEgress:
    """ADR-0014 section 2. Trusted operator/domain configuration, never
    repository-controlled configuration."""
    provider_class: ProviderClass
    provider_principal_binding: str
    allowed_model_ids: tuple[str, ...]
    allowed_model_families: tuple[str, ...]
    allowed_routing_classes: tuple[str, ...]
    allowed_endpoint_policy: str
    allowed_egress_class: str
    dynamic_routing_policy: str
    fallback_policy: str

    def digest(self) -> str:
        normalized = {
            **asdict(self),
            "provider_class": self.provider_class.value,
            "allowed_model_ids": sorted(self.allowed_model_ids),
            "allowed_model_families": sorted(self.allowed_model_families),
            "allowed_routing_classes": sorted(self.allowed_routing_classes),
        }
        return digest({"schema_version": SCHEMA_VERSION, **normalized})


@dataclass(frozen=True)
class CarriedStateContract:
    """ADR-0014 section 9. The Phase A -> Phase B binding; every re-measurable
    property here must actually be re-measured before releasing sensitive context."""
    harness_binary_identity: str
    harness_version: str
    config_root_digest: str
    provider_principal: str
    effective_model_id: str
    routing_class: str
    endpoint_policy_digest: str
    plugin_inventory_digest: str
    adapter_version: str
    probe_version: str

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})


def persistence_namespace(domain: SecurityDomain, exposure_digest: str, memory_digest: str, assurance_digest: str) -> str:
    """Exact-match namespace; callers must explicitly migrate incompatible state."""
    return digest({"schema_version": SCHEMA_VERSION, "domain": domain.identity_digest(), "exposure": exposure_digest, "memory": memory_digest, "assurance": assurance_digest})


def allowed_context_envelope_from_authoritative_roots(
    repository_roots: tuple[str, ...],
    vault_memory_roots: tuple[str, ...],
) -> AllowedContextEnvelope:
    """Materialize the operator envelope from authoritative roots only.

    Pure materialization: the exact authoritative values go in and come out;
    it selects nothing and fails closed when an authoritative root is absent.
    """
    if not repository_roots or not vault_memory_roots:
        raise ValueError("authoritative repository and vault roots are both required")
    return AllowedContextEnvelope(
        repository_roots=tuple(repository_roots),
        vault_memory_roots=tuple(vault_memory_roots),
    )


def policy_digest(policy: dict[str, Any]) -> str:
    """Policy callers supply the full normalized object; subsets are not accepted here.

    Kept as a plain function for callers that only need the digest value;
    MemoryPolicyDigest above wraps the identical computation as a named type.
    """
    return digest({"schema_version": SCHEMA_VERSION, "policy": policy})
