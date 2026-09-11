"""Thin `ainative exec` orchestration layer.

This module contains no security policy. It resolves nothing, qualifies
nothing and emits nothing: it invokes the frozen SensitiveLaunchGate and
propagates its exact decision. The RuntimeContextHandle and the
AllowedContextEnvelope are the objects produced by Runtime Authority and
carried through by the gate - never rebuilt here.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .sensitive_launch import (
    ALLOW_PHASE_B,
    DENY_RUNTIME_AUTHORITY_LOST,
    SensitiveLaunchGate,
)

PHASE_A_READY = "PHASE_A_READY"


@dataclass(frozen=True)
class ExecOutcome:
    decision: str
    denial_code: object
    spawned: bool
    runtime_context_handle: Any = None
    allowed_context_envelope: Any = None
    env: Mapping[str, str] = field(default_factory=dict)
    denial_detail: object = None


def execute_sensitive(
    *,
    workspace: Any,
    security_domain_id: str,
    checkout_identity: Any,
    authority: Any,
    envelope: Any,
    argv: Sequence[str],
    base_env: Mapping[str, str],
    measure: Callable[[], Mapping[str, str]],
    spawn: Callable[..., Any],
    launcher_alive: Callable[[], bool] | None = None,
    authority_alive: Callable[[], bool] | None = None,
) -> ExecOutcome:
    gate_kwargs = {}
    if launcher_alive is not None:
        gate_kwargs["launcher_alive"] = launcher_alive
    if authority_alive is not None:
        gate_kwargs["authority_alive"] = authority_alive
    gate = SensitiveLaunchGate(
        workspace=workspace,
        security_domain_id=security_domain_id,
        checkout_identity=checkout_identity,
        authority=authority,
        envelope=envelope,
        measure=measure,
        **gate_kwargs,
    )
    first = gate.phase_a()
    if first.decision != PHASE_A_READY:
        return ExecOutcome(decision=first.decision, denial_code=first.decision, denial_detail=first.denial_reason, spawned=False)
    final = gate.phase_b()
    if final.decision != ALLOW_PHASE_B:
        return ExecOutcome(decision=final.decision, denial_code=final.decision, denial_detail=final.denial_reason, spawned=False)
    handle = final.runtime_context_handle
    allowed_envelope = final.allowed_context_envelope
    if handle is None or allowed_envelope is None:
        return ExecOutcome(decision=DENY_RUNTIME_AUTHORITY_LOST, denial_code=DENY_RUNTIME_AUTHORITY_LOST, spawned=False)
    child_env = dict(base_env)
    spawn(
        argv=list(argv),
        env=child_env,
        runtime_context_handle=handle,
        allowed_context_envelope=allowed_envelope,
    )
    return ExecOutcome(
        decision=final.decision,
        denial_code=None,
        spawned=True,
        runtime_context_handle=handle,
        allowed_context_envelope=allowed_envelope,
        env=child_env,
    )