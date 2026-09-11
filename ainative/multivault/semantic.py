"""Semantic provider admission, drift revocation and retrieval confinement (MV-14).

MV-00.2 currently reports Smart Connections 4.7.2 with no runtime observation
mechanism (`semantic_background_egress = UNKNOWN`), so sensitive semantic
admission denies by default. See ADR-0015 sections 7 and 8.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .schema import SecurityClassification


@dataclass(frozen=True)
class SemanticProviderProfile:
    """Probe-backed inspector snapshot for one plugin/provider version."""

    plugin: str
    plugin_version: str
    provider: str
    endpoint: str
    indexing_mode: str
    background_behavior: str
    store_location: str
    observer_available: bool
    egress_config_digest: str
    evidence_digest: str

    def is_qualified(self) -> bool:
        return bool(
            self.plugin
            and self.plugin_version
            and self.provider
            and self.endpoint
            and self.indexing_mode
            and self.background_behavior
            and self.store_location
            and self.observer_available
            and self.egress_config_digest
            and self.evidence_digest
        )


@dataclass(frozen=True)
class SemanticAdmission:
    decision: str
    reason: str


class ObservationStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    CONFIGURATION_UNREADABLE = "configuration_unreadable"
    OBSERVER_UNAVAILABLE = "observer_unavailable"


@dataclass(frozen=True)
class SemanticObservation:
    status: ObservationStatus
    egress_digest: str | None = None


def admit_semantic_session(
    profile: SemanticProviderProfile | None,
    classification: SecurityClassification,
    *,
    approved_egress_digest: str | None = None,
) -> SemanticAdmission:
    """Fail closed: TEAM and above require a probe-qualified, approved profile."""
    if classification is SecurityClassification.PERSONAL:
        return SemanticAdmission("ALLOW", "personal classification records the semantic profile without an observer requirement")
    if profile is None:
        return SemanticAdmission("DENY", "no semantic provider profile is configured for the active vault")
    if not profile.is_qualified():
        return SemanticAdmission("DENY", f"{profile.plugin or 'unknown plugin'} semantic provider is not probe-qualified")
    if not approved_egress_digest:
        return SemanticAdmission("DENY", "no trusted approved semantic egress digest is configured")
    if profile.egress_config_digest != approved_egress_digest:
        return SemanticAdmission("DENY", "semantic egress config does not match the approved digest")
    return SemanticAdmission("ALLOW", "semantic provider, egress config and observer are qualified")


def semantic_revocation(
    recorded_egress_digest: str,
    observation: SemanticObservation,
) -> str | None:
    """Return the revocation reason when the governed session must be revoked."""
    if not recorded_egress_digest:
        return "missing recorded semantic egress digest"
    if observation.status is ObservationStatus.CONFIGURATION_UNREADABLE:
        return "semantic configuration unreadable"
    if observation.status is ObservationStatus.OBSERVER_UNAVAILABLE:
        return "semantic observer unavailable"
    if observation.status is ObservationStatus.CHANGED:
        return "semantic egress drift"
    if observation.egress_digest != recorded_egress_digest:
        return "semantic egress digest mismatch"
    return None