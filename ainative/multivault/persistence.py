"""Opaque, exact-match persistent-store isolation for Multi-Vault.

ADR-0013 section 8: the namespace derives from SecurityDomainIdentity +
ContextExposureDigest + MemoryPolicyDigest + PersistenceAssuranceDigest. A
mismatch never auto-loads; changing namespace requires an explicit, recorded
migration decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .schema import (
    AllowedContextEnvelope,
    MemoryPolicyDigest,
    PersistenceAssuranceDigest,
    SecurityDomain,
    persistence_namespace,
)

STORE_HEADER_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StoreNamespace:
    domain_digest: str
    context_exposure_digest: str
    memory_policy_digest: str
    assurance_digest: str
    namespace_digest: str

    def path_segments(self) -> tuple[str, str, str, str]:
        return (self.domain_digest, self.context_exposure_digest, self.memory_policy_digest, self.assurance_digest)


@dataclass(frozen=True)
class StoreHeader:
    schema_version: int
    namespace_digest: str

    def encode(self) -> str:
        return json.dumps({"schema_version": self.schema_version, "namespace_digest": self.namespace_digest}, sort_keys=True, separators=(",", ":")) + "\n"

    @staticmethod
    def decode(payload: str) -> "StoreHeader":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("store header is not valid JSON") from error
        if not isinstance(data, dict) or data.get("schema_version") != STORE_HEADER_SCHEMA_VERSION:
            raise ValueError("store header schema is unsupported")
        namespace_digest = data.get("namespace_digest")
        if not isinstance(namespace_digest, str) or not namespace_digest:
            raise ValueError("store header namespace digest is missing")
        return StoreHeader(STORE_HEADER_SCHEMA_VERSION, namespace_digest)


@dataclass(frozen=True)
class LoadDecision:
    decision: str
    reason: str


@dataclass(frozen=True)
class MigrationPlan:
    from_digest: str
    to_digest: str


def namespace_for(
    domain: SecurityDomain,
    envelope: AllowedContextEnvelope,
    memory_policy: MemoryPolicyDigest,
    assurance: PersistenceAssuranceDigest,
) -> StoreNamespace:
    exposure_digest = envelope.exposure_digest()
    memory_digest = memory_policy.digest()
    assurance_digest = assurance.digest()
    return StoreNamespace(
        domain.identity_digest(),
        exposure_digest,
        memory_digest,
        assurance_digest,
        persistence_namespace(domain, exposure_digest, memory_digest, assurance_digest),
    )


def namespace_path(root: Path, namespace: StoreNamespace) -> Path:
    return root.joinpath(*namespace.path_segments())


def admit_load(header: StoreHeader, namespace: StoreNamespace) -> LoadDecision:
    if header.schema_version != STORE_HEADER_SCHEMA_VERSION:
        return LoadDecision("REFUSE", "unsupported store header schema version")
    if header.namespace_digest != namespace.namespace_digest:
        return LoadDecision("REFUSE", "namespace mismatch; explicit migration decision required")
    return LoadDecision("LOAD", "exact namespace match")


def plan_migration(header: StoreHeader, namespace: StoreNamespace) -> MigrationPlan | None:
    if header.namespace_digest == namespace.namespace_digest:
        return None
    return MigrationPlan(header.namespace_digest, namespace.namespace_digest)


def apply_migration(plan: MigrationPlan, *, operator_approval_reference: str) -> StoreHeader:
    if not operator_approval_reference:
        raise ValueError("namespace migration requires an explicit operator approval reference")
    return StoreHeader(STORE_HEADER_SCHEMA_VERSION, plan.to_digest)