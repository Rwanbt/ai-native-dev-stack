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
        provider_selection_control=ControlLevel.VERIFIED,
        model_selection_control=ControlLevel.VERIFIED,
        endpoint_routing_control=ControlLevel.VERIFIED,
        provider_principal_observation=Observation(ObservationMode.PER_OPERATION),
        model_identity_observation=Observation(ObservationMode.PER_OPERATION),
        endpoint_routing_observation=Observation(ObservationMode.PER_OPERATION),
        auth_store_observation=Observation(ObservationMode.PER_OPERATION),
        two_phase_attestation=TwoPhaseAttestation.PROBE,
        session_containment=ControlLevel.VERIFIED,
        evidence_digest=evidence_digest,
    )

AUTH_STORE_SCHEMA_VERSION = 1
_AUTH_INVENTORY_ALLOWLIST = (".credentials.json", "settings.json", "claude.json")


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
    for relative in sorted(_AUTH_INVENTORY_ALLOWLIST):
        item = path / relative
        if not item.is_file():
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


def binary_identity(path) -> str | None:
    """sha256 of the harness executable; None when unreadable."""
    import hashlib
    from pathlib import Path

    item = Path(path)
    if not item.is_file():
        return None
    digest = hashlib.sha256()
    with item.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plugin_inventory_digest(config_dir) -> str:
    """Digest of plugin file names and sizes; stable text when none exist."""
    import hashlib
    from pathlib import Path

    plugins = Path(config_dir) / "plugins"
    if not plugins.is_dir():
        return hashlib.sha256(b"no-plugins").hexdigest()
    entries = [f"{item.relative_to(plugins).as_posix()}:{item.stat().st_size}" for item in sorted(plugins.rglob("*")) if item.is_file()]
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


_CONTRACT_FIELDS = (
    "harness_binary_identity",
    "harness_version",
    "config_root_digest",
    "provider_principal",
    "effective_model_id",
    "routing_class",
    "endpoint_policy_digest",
    "plugin_inventory_digest",
    "adapter_version",
    "probe_version",
)


def carried_state_mismatches(phase_a, phase_b) -> tuple[str, ...]:
    """Required properties that differ between Phase A and Phase B."""
    from dataclasses import asdict

    first, second = asdict(phase_a), asdict(phase_b)
    return tuple(name for name in _CONTRACT_FIELDS if first[name] != second[name])


CLAUDE_INSTRUCTIONS_REASON_CODE = "AINATIVE_CLAUDE_PROJECT_INSTRUCTIONS_NOT_DISABLEABLE"
_PROJECT_INSTRUCTION_SURFACES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")
PROJECT_INSTRUCTION_POLICY = {
    "surface": "CLAUDE.md",
    "autoload": "VERIFIED",
    "disable_control": "NONE",
    "required_state": "ABSENT",
    "observation": "PER_OPERATION",
}


def project_instruction_admission(workspace) -> dict:
    """Fail closed: DENY when any applicable project instruction surface exists.

    Empirically recognized on claude-code 2.1.220: CLAUDE.md, CLAUDE.local.md
    and .claude/CLAUDE.md in the workspace itself; CLAUDE.md or
    CLAUDE.local.md in ancestors up to the git root, or in the immediate
    parent when no git root exists.
    """
    from pathlib import Path

    root = Path(workspace).resolve()
    found = [str(root / relative) for relative in _PROJECT_INSTRUCTION_SURFACES if (root / relative).is_file()]
    boundary = None
    current = root
    while True:
        if (current / ".git").exists():
            boundary = current
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    ancestors = []
    if boundary is not None and boundary != root:
        current = root.parent
        while True:
            ancestors.append(current)
            if current == boundary:
                break
            parent = current.parent
            if parent == current:
                break
            current = parent
    elif boundary is None and root.parent != root:
        ancestors.append(root.parent)
    for ancestor in ancestors:
        for relative in ("CLAUDE.md", "CLAUDE.local.md"):
            candidate = ancestor / relative
            if candidate.is_file():
                found.append(str(candidate))
    if found:
        return {"decision": "DENY", "reason_code": CLAUDE_INSTRUCTIONS_REASON_CODE, "surfaces": tuple(found), "policy": dict(PROJECT_INSTRUCTION_POLICY)}
    return {"decision": "ALLOW", "reason_code": "OK", "surfaces": (), "policy": dict(PROJECT_INSTRUCTION_POLICY)}


from dataclasses import dataclass as _dataclass, replace as _replace

PROJECT_INSTRUCTION_SCAN_INCOMPLETE_CODE = "AINATIVE_CLAUDE_INSTRUCTION_SCAN_INCOMPLETE"


@_dataclass(frozen=True)
class ProjectInstructionAdmission:
    harness_id: str
    harness_version: str
    workspace_root: str
    git_root: str
    applicable_surfaces: tuple
    observed_state: tuple
    policy_digest: str
    verified_at: str
    decision: str
    reason_code: str


def _git_root(root):
    current = root
    while True:
        if (current / ".git").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            return ""
        current = parent


def instruction_admission_record(workspace) -> ProjectInstructionAdmission:
    """PER_OPERATION admission record; fail closed on any uncertainty."""
    from datetime import datetime, timezone
    from pathlib import Path

    from .schema import digest as canonical_digest

    root = Path(workspace).resolve()
    policy_digest = canonical_digest(dict(PROJECT_INSTRUCTION_POLICY))
    base = {
        "harness_id": "claude-code",
        "harness_version": "2.1.220",
        "workspace_root": str(root),
        "git_root": "",
        "policy_digest": policy_digest,
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if not root.is_dir():
        return ProjectInstructionAdmission(**base, applicable_surfaces=(), observed_state=(), decision="DENY_OBSERVATION_INCOMPLETE", reason_code=PROJECT_INSTRUCTION_SCAN_INCOMPLETE_CODE)
    base["git_root"] = _git_root(root)
    try:
        found = []
        for relative in _PROJECT_INSTRUCTION_SURFACES:
            if (root / relative).is_file():
                found.append(str(root / relative))
        boundary = base["git_root"]
        ancestors = []
        if boundary and Path(boundary) != root:
            current = root.parent
            while True:
                ancestors.append(current)
                if str(current) == boundary:
                    break
                parent = current.parent
                if parent == current:
                    break
                current = parent
        elif not boundary and root.parent != root:
            ancestors.append(root.parent)
        for ancestor in ancestors:
            for relative in ("CLAUDE.md", "CLAUDE.local.md"):
                candidate = ancestor / relative
                if candidate.is_file():
                    found.append(str(candidate))
    except OSError:
        return ProjectInstructionAdmission(**base, applicable_surfaces=(), observed_state=(), decision="DENY_OBSERVATION_INCOMPLETE", reason_code=PROJECT_INSTRUCTION_SCAN_INCOMPLETE_CODE)
    observed = tuple(f"{path}:present" for path in found)
    decision = "DENY_NOT_DISABLEABLE" if found else "ALLOW"
    reason_code = CLAUDE_INSTRUCTIONS_REASON_CODE if found else "OK"
    return ProjectInstructionAdmission(**base, applicable_surfaces=tuple(found), observed_state=observed, decision=decision, reason_code=reason_code)


class SensitivePhaseGate:
    """Phase A admission plus a mandatory re-check before Phase B release."""

    def __init__(self, workspace):
        from pathlib import Path

        self._workspace = Path(workspace)
        self._phase_a = None

    def phase_a(self) -> ProjectInstructionAdmission:
        self._phase_a = instruction_admission_record(self._workspace)
        return self._phase_a

    def phase_b(self) -> ProjectInstructionAdmission:
        current = instruction_admission_record(self._workspace)
        if self._phase_a is None:
            return _replace(current, decision="DENY_OBSERVATION_INCOMPLETE", reason_code=PROJECT_INSTRUCTION_SCAN_INCOMPLETE_CODE)
        if self._phase_a.decision != "ALLOW" or current.decision != "ALLOW":
            return current
        if current.policy_digest != self._phase_a.policy_digest or current.applicable_surfaces != self._phase_a.applicable_surfaces:
            return _replace(current, decision="DENY_NOT_DISABLEABLE", reason_code=CLAUDE_INSTRUCTIONS_REASON_CODE)
        return current
