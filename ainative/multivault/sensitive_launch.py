"""Integrated sensitive launch gate for the probed Claude tuple (MV-07/08/12 wiring).

Orchestrates Phase A (neutral) evidence, the project-instruction policy, the
provider/model/endpoint/auth-store/containment qualifications and the
carried-state revalidation before any sensitive release. The gate returns the
RuntimeContextHandle and the AllowedContextEnvelope ONLY on ALLOW_PHASE_B;
every denial returns neither. This aggregate object is evidence, not a new
authority source: Runtime Authority still issues handles, ContextPlanner still
selects context.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from .harness_claude import instruction_admission_record
from .runtime_authority import (
    ImmutableAuthoritativeSecurityState,
    RuntimeAuthority,
    RuntimeContextHandle,
    SensitiveQualification,
)
from .schema import AllowedContextEnvelope, digest as canonical_digest


ALLOW_PHASE_B = "ALLOW_PHASE_B"
DENY_PROJECT_INSTRUCTIONS = "DENY_PROJECT_INSTRUCTIONS"
DENY_PROVIDER_IDENTITY = "DENY_PROVIDER_IDENTITY"
DENY_MODEL_IDENTITY = "DENY_MODEL_IDENTITY"
DENY_ENDPOINT_ROUTING = "DENY_ENDPOINT_ROUTING"
DENY_AUTH_STORE = "DENY_AUTH_STORE"
DENY_CARRIED_STATE_DRIFT = "DENY_CARRIED_STATE_DRIFT"
DENY_CONTAINMENT = "DENY_CONTAINMENT"
DENY_OBSERVATION_INCOMPLETE = "DENY_OBSERVATION_INCOMPLETE"
DENY_RUNTIME_AUTHORITY_LOST = "DENY_RUNTIME_AUTHORITY_LOST"

CARRIED_STATE_FIELDS = (
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


@dataclass(frozen=True)
class SensitiveLaunchAdmission:
    security_domain_id: str
    checkout_identity: str
    harness_identity: str
    phase_a_evidence_digest: str
    project_instruction_policy_digest: str
    provider_qualification_digest: str
    model_qualification_digest: str
    endpoint_qualification_digest: str
    auth_store_qualification_digest: str
    carried_state_digest: str
    containment_evidence_digest: str
    decision: str
    denial_reason: str
    verified_at: str
    carried_state_mismatches: tuple
    runtime_context_handle: RuntimeContextHandle | None = None
    allowed_context_envelope: AllowedContextEnvelope | None = None


class SensitiveLaunchGate:
    """Phase A discovery plus the mandatory pre-Phase-B revalidation."""

    def __init__(
        self,
        *,
        workspace,
        security_domain_id: str,
        checkout_identity: str,
        authority: RuntimeAuthority,
        envelope: AllowedContextEnvelope,
        measure: Callable[[], Mapping[str, str]],
        launcher_alive: Callable[[], bool] = lambda: True,
        authority_alive: Callable[[], bool] = lambda: True,
    ):
        self._workspace = workspace
        self._domain = security_domain_id
        self._checkout = checkout_identity
        self._authority = authority
        self._envelope = envelope
        self._measure = measure
        self._launcher_alive = launcher_alive
        self._authority_alive = authority_alive
        self._phase_a: Mapping[str, str] | None = None
        self._phase_a_evidence_digest: str = ""

    def _result(self, decision: str, reason: str, mismatches: tuple = (), handle=None, envelope=None) -> SensitiveLaunchAdmission:
        return SensitiveLaunchAdmission(
            security_domain_id=self._domain,
            checkout_identity=self._checkout,
            harness_identity="claude-code",
            phase_a_evidence_digest=self._phase_a_evidence_digest,
            project_instruction_policy_digest=canonical_digest(instruction_admission_record(self._workspace).policy_digest),
            provider_qualification_digest=canonical_digest({"provider_principal": (self._phase_a or {}).get("provider_principal")}),
            model_qualification_digest=canonical_digest({"effective_model_id": (self._phase_a or {}).get("effective_model_id")}),
            endpoint_qualification_digest=canonical_digest({"endpoint_policy_digest": (self._phase_a or {}).get("endpoint_policy_digest")}),
            auth_store_qualification_digest=canonical_digest({"config_root_digest": (self._phase_a or {}).get("config_root_digest")}),
            carried_state_digest=canonical_digest({field: (self._phase_a or {}).get(field) for field in CARRIED_STATE_FIELDS}),
            containment_evidence_digest=canonical_digest({"containment_ok": (self._phase_a or {}).get("containment_ok")}),
            decision=decision,
            denial_reason=reason,
            verified_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            carried_state_mismatches=mismatches,
            runtime_context_handle=handle,
            allowed_context_envelope=envelope,
        )

    def phase_a(self) -> SensitiveLaunchAdmission:
        instructions = instruction_admission_record(self._workspace)
        if instructions.decision == "DENY_OBSERVATION_INCOMPLETE":
            return self._result(DENY_OBSERVATION_INCOMPLETE, instructions.reason_code)
        if instructions.decision != "ALLOW":
            return self._result(DENY_PROJECT_INSTRUCTIONS, instructions.reason_code)
        try:
            measured = dict(self._measure())
        except OSError:
            return self._result(DENY_OBSERVATION_INCOMPLETE, "phase A measurement failed")
        missing = [key for key in CARRIED_STATE_FIELDS if not measured.get(key)]
        if missing:
            return self._result(DENY_OBSERVATION_INCOMPLETE, f"missing measurements: {','.join(missing)}")
        self._phase_a = measured
        self._phase_a_evidence_digest = canonical_digest({field: measured.get(field) for field in CARRIED_STATE_FIELDS})
        for flag, code in (("provider_ok", DENY_PROVIDER_IDENTITY), ("model_ok", DENY_MODEL_IDENTITY), ("endpoint_ok", DENY_ENDPOINT_ROUTING), ("auth_store_ok", DENY_AUTH_STORE), ("containment_ok", DENY_CONTAINMENT)):
            if measured.get(flag) != "true":
                return self._result(code, f"qualification failed: {flag}")
        return self._result("PHASE_A_READY", "phase A evidence complete; sensitive release still withheld")

    def phase_b(self) -> SensitiveLaunchAdmission:
        if self._phase_a is None:
            return self._result(DENY_OBSERVATION_INCOMPLETE, "phase A was not completed")
        if not self._launcher_alive() or not self._authority_alive():
            return self._result(DENY_RUNTIME_AUTHORITY_LOST, "launcher or runtime authority is not alive")
        instructions = instruction_admission_record(self._workspace)
        if instructions.decision == "DENY_OBSERVATION_INCOMPLETE":
            return self._result(DENY_OBSERVATION_INCOMPLETE, instructions.reason_code)
        if instructions.decision != "ALLOW":
            return self._result(DENY_PROJECT_INSTRUCTIONS, instructions.reason_code)
        try:
            measured = dict(self._measure())
        except OSError:
            return self._result(DENY_OBSERVATION_INCOMPLETE, "phase B measurement failed")
        mismatches = tuple(field for field in CARRIED_STATE_FIELDS if measured.get(field) != self._phase_a.get(field))
        if mismatches:
            return self._result(DENY_CARRIED_STATE_DRIFT, f"carried-state drift: {','.join(mismatches)}", mismatches)
        for flag, code in (("provider_ok", DENY_PROVIDER_IDENTITY), ("model_ok", DENY_MODEL_IDENTITY), ("endpoint_ok", DENY_ENDPOINT_ROUTING), ("auth_store_ok", DENY_AUTH_STORE), ("containment_ok", DENY_CONTAINMENT)):
            if measured.get(flag) != "true":
                return self._result(code, f"qualification failed before release: {flag}")
        handle = self._authority.issue_phase_b_handle(self._checkout, SensitiveQualification(True, True, True))
        if handle is None:
            return self._result(DENY_RUNTIME_AUTHORITY_LOST, "runtime authority refused handle issuance")
        return self._result(ALLOW_PHASE_B, "all gates passed", handle=handle, envelope=self._envelope)