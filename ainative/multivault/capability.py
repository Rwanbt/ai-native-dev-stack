"""Versioned, probe-backed capability manifests for sensitive Multi-Vault admission."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ControlLevel(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    VERIFIED = "verified"


class ObservationMode(str, Enum):
    NONE = "none"
    EVENT = "event"
    PER_OPERATION = "per_operation"
    POLL = "poll"


class TwoPhaseAttestation(str, Enum):
    NONE = "none"
    STATIC = "static"
    PROBE = "probe"


@dataclass(frozen=True)
class CapabilityTuple:
    harness: str
    harness_version: str
    provider: str
    platform: str
    adapter_version: str
    probe_version: str

    def is_complete(self) -> bool:
        return all(
            (
                self.harness,
                self.harness_version,
                self.provider,
                self.platform,
                self.adapter_version,
                self.probe_version,
            )
        )


@dataclass(frozen=True)
class Observation:
    mode: ObservationMode
    max_interval_seconds: int | None = None

    def is_bounded(self) -> bool:
        if self.mode in (ObservationMode.EVENT, ObservationMode.PER_OPERATION):
            return True
        return self.mode is ObservationMode.POLL and bool(
            self.max_interval_seconds and self.max_interval_seconds > 0
        )


@dataclass(frozen=True)
class CapabilityManifest:
    capability_tuple: CapabilityTuple
    provider_selection_control: ControlLevel
    model_selection_control: ControlLevel
    endpoint_routing_control: ControlLevel
    provider_principal_observation: Observation
    model_identity_observation: Observation
    endpoint_routing_observation: Observation
    auth_store_observation: Observation
    two_phase_attestation: TwoPhaseAttestation
    session_containment: ControlLevel
    evidence_digest: str

    def sensitive_eligible(self) -> bool:
        """Fail closed: every required assertion must be exact and observable."""
        controls = (
            self.provider_selection_control,
            self.model_selection_control,
            self.endpoint_routing_control,
            self.session_containment,
        )
        observations = (
            self.provider_principal_observation,
            self.model_identity_observation,
            self.endpoint_routing_observation,
            self.auth_store_observation,
        )
        return (
            self.capability_tuple.is_complete()
            and all(control is ControlLevel.VERIFIED for control in controls)
            and all(observation.is_bounded() for observation in observations)
            and self.two_phase_attestation is not TwoPhaseAttestation.NONE
            and bool(self.evidence_digest)
        )


class CapabilityRegistry:
    """Trusted in-memory registry; unknown tuples never inherit another version's proof."""

    def __init__(self) -> None:
        self._manifests: dict[CapabilityTuple, CapabilityManifest] = {}

    def register(self, manifest: CapabilityManifest) -> None:
        if not manifest.capability_tuple.is_complete():
            raise ValueError("capability tuple must include every versioned identity")
        self._manifests[manifest.capability_tuple] = manifest

    def sensitive_admission(self, capability_tuple: CapabilityTuple) -> str:
        manifest = self._manifests.get(capability_tuple)
        if manifest is None or not manifest.sensitive_eligible():
            return "DENY"
        return "ALLOW"
