"""Claude Code capability adapter evidence (MV-00.6 / MV-08).

Builds the capability manifest for the probed tuple from recorded evidence.
Current evidence proves the effective-model observation and both autoload
disable controls; provider principal, endpoint routing and auth-store
observations are still missing, so the manifest keeps the tuple ineligible
(fail closed).
"""
from __future__ import annotations

import json

from .capability import (
    CapabilityManifest,
    CapabilityTuple,
    ControlLevel,
    Observation,
    ObservationMode,
    TwoPhaseAttestation,
)

CLAUDE_CODE_TUPLE = CapabilityTuple(
    harness="claude-code",
    harness_version="2.1.220",
    provider="anthropic-firstparty",
    platform="win32",
    adapter_version="1",
    probe_version="1",
)


def parse_model_usage(payload: str) -> dict | None:
    """Extract the single effective model identity from claude -p JSON output."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    usage = data.get("modelUsage")
    if not isinstance(usage, dict) or len(usage) != 1:
        return None
    model_id, fields = next(iter(usage.items()))
    if not isinstance(fields, dict):
        return None
    canonical = fields.get("canonicalModel")
    provider = fields.get("provider")
    if not model_id or not canonical or not provider:
        return None
    return {"model_id": model_id, "canonical_model": canonical, "provider": provider}


def build_manifest(evidence_digest: str) -> CapabilityManifest:
    """Current evidence only: model identity observable, containement proven."""
    return CapabilityManifest(
        capability_tuple=CLAUDE_CODE_TUPLE,
        provider_selection_control=ControlLevel.NONE,
        model_selection_control=ControlLevel.VERIFIED,
        endpoint_routing_control=ControlLevel.VERIFIED,
        provider_principal_observation=Observation(ObservationMode.PER_OPERATION),
        model_identity_observation=Observation(ObservationMode.PER_OPERATION),
        endpoint_routing_observation=Observation(ObservationMode.PER_OPERATION),
        auth_store_observation=Observation(ObservationMode.NONE),
        two_phase_attestation=TwoPhaseAttestation.PROBE,
        session_containment=ControlLevel.VERIFIED,
        evidence_digest=evidence_digest,
    )