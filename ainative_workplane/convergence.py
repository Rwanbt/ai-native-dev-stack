"""PR-05 deterministic convergence decision."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .evidence import VerificationEvidence
from .freshness import FreshnessResult
from .traceability import Gap, TraceabilityResult
from .trust import TrustVerdict


BLOCKING_FRESHNESS = frozenset({
    "FRESHNESS_UNAVAILABLE",
    "STALE_CONTRACT",
    "STALE_SCOPE",
    "STALE_DEPENDENCY",
    "COMMAND_REGISTRY_CHANGED",
    "POLICY_CHANGED",
    "ROOT_OF_TRUST_CHANGED",
})


@dataclass(frozen=True)
class ConvergenceVerdict:
    verdict: str
    gaps: tuple[Gap, ...]
    reason: str
    fingerprint: str = ""


def stall_fingerprint(gaps: Iterable[Gap]) -> str:
    payload = [{"code": gap.code, "uid": gap.uid, "detail": gap.detail} for gap in gaps]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def converge(traceability: TraceabilityResult, runs: Iterable[VerificationEvidence], *, freshness: FreshnessResult | None = None, trust: TrustVerdict | None = None) -> ConvergenceVerdict:
    """Decide convergence from bound evidence only.

    @contract Evidence supports convergence only when its verification
    specification is declared by the contract graph, and every declared
    specification carries passing evidence.
    """

    gaps = list(traceability.gaps)
    if traceability.requirement_count == 0:
        gaps.append(Gap("NO_MEANINGFUL_REQUIREMENTS", None, "a work contract requires at least one requirement"))
    states = set(freshness.states) if freshness is not None else {"FRESHNESS_UNAVAILABLE"}
    for state in sorted(states & BLOCKING_FRESHNESS):
        gaps.append(Gap(state, None, "blocking freshness state"))
    if trust is None:
        gaps.append(Gap("ROOT_OF_TRUST_INVALID", None, "no trust evaluation is available"))
    elif not trust.trusted:
        gaps.append(Gap(trust.code, None, "evidence authority is insufficient"))
    run_list = list(runs)
    if not run_list:
        gaps.append(Gap("NO_VERIFICATION_EVIDENCE", None, "no selected verification evidence is available"))
        return ConvergenceVerdict("NOT_CONVERGED", tuple(gaps), "no verification run is available", stall_fingerprint(gaps))
    declared_specs = {spec_uid for _, spec_uid in traceability.acceptance_to_verification}
    passed_specs: set[str] = set()
    for run in run_list:
        if not isinstance(run, VerificationEvidence):
            gaps.append(Gap("INVALID_VERIFICATION_EVIDENCE", None, "selected run is not validated evidence"))
            continue
        spec_uid = run.verification_specification_uid
        if spec_uid not in declared_specs:
            gaps.append(Gap("UNRELATED_VERIFICATION_EVIDENCE", run.uid, "evidence is bound to a specification the contract does not declare"))
        elif run.result != "PASS":
            gaps.append(Gap("VERIFICATION_FAILED", run.uid, "selected verification did not pass"))
        else:
            passed_specs.add(spec_uid)
    for spec_uid in sorted(declared_specs - passed_specs):
        gaps.append(Gap("UNVERIFIED_SPECIFICATION", spec_uid, "declared verification specification has no passing evidence"))
    if gaps:
        return ConvergenceVerdict("NOT_CONVERGED", tuple(gaps), "structural, freshness, or verification gaps remain", stall_fingerprint(gaps))
    return ConvergenceVerdict("CONVERGED", (), "all deterministic conditions satisfied", "")


def append_convergence(path: str | Path, verdict: ConvergenceVerdict, *, work_uid: str, engine_version: str) -> None:
    """Append a historical convergence fact; never overwrite an earlier run."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"work_uid": work_uid, "verdict": verdict.verdict, "reason": verdict.reason, "fingerprint": verdict.fingerprint, "engine_version": engine_version}
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
