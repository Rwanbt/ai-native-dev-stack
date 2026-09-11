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

AUTH_STORE_SCHEMA_VERSION = 1
_AUTH_INVENTORY_SKIP = {".git", "cache", "shell-snapshots", "statsig", "todos", "projects", "history.jsonl", "file-history"}


def auth_store_identity(config_dir) -> str | None:
    """Canonical store identity: schema version, canonical path, inventory digest.

    Only digests are computed; no secret or file content is recorded.
    """
    import hashlib
    import os
    from pathlib import Path

    path = Path(config_dir)
    if not path.is_dir():
        return None
    canonical = os.path.normcase(str(path.resolve()))
    entries = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(path).as_posix()
        if any(part in _AUTH_INVENTORY_SKIP for part in relative.split("/")):
            continue
        try:
            content = item.read_bytes()
        except OSError:
            return None
        entries.append(f"{relative}:{len(content)}:{hashlib.sha256(content).hexdigest()}")
    inventory = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return hashlib.sha256(f"{AUTH_STORE_SCHEMA_VERSION}|{canonical}|{inventory}".encode("utf-8")).hexdigest()


def parse_auth_status(payload: str) -> dict | None:
    import hashlib
    import json

    try:
        data = json.loads(payload.strip().lstrip("\ufeff"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "loggedIn" not in data:
        return None
    principal = None
    if data.get("loggedIn") and data.get("email") and data.get("orgId"):
        principal = hashlib.sha256(f"{data['email']}|{data['orgId']}".encode()).hexdigest()
    return {"logged_in": bool(data["loggedIn"]), "api_provider": data.get("apiProvider"), "principal_digest": principal}


def binding_matches(phase_a_identity: str | None, phase_b_identity: str | None) -> bool:
    return bool(phase_a_identity) and phase_a_identity == phase_b_identity
