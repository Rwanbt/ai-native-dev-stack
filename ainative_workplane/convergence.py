"""PR-05 deterministic convergence decision."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .evidence import VerificationEvidence
from .traceability import Gap, TraceabilityResult
from .trust import TrustVerdict


BLOCKING_FRESHNESS = frozenset({"STALE_CONTRACT", "STALE_SCOPE", "STALE_DEPENDENCY", "COMMAND_REGISTRY_CHANGED", "POLICY_CHANGED"})


@dataclass(frozen=True)
class ConvergenceVerdict:
    verdict: str
    gaps: tuple[Gap, ...]
    reason: str
    fingerprint: str = ""


def stall_fingerprint(gaps: Iterable[Gap]) -> str:
    payload = [{"code": gap.code, "uid": gap.uid, "detail": gap.detail} for gap in gaps]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def converge(traceability: TraceabilityResult, runs: Iterable[VerificationEvidence], *, freshness: Iterable[str] = (), trust: TrustVerdict | None = None) -> ConvergenceVerdict:
    gaps = list(traceability.gaps)
    states = set(freshness)
    for state in sorted(states & BLOCKING_FRESHNESS):
        gaps.append(Gap(state, None, "blocking freshness state"))
    if trust is None:
        gaps.append(Gap("ROOT_OF_TRUST_INVALID", None, "no trust evaluation is available"))
    elif not trust.trusted:
        gaps.append(Gap(trust.code, None, "evidence authority is insufficient"))
    run_list = list(runs)
    if not run_list:
        return ConvergenceVerdict("INVALID", tuple(gaps), "no verification run is available", stall_fingerprint(gaps))
    for run in run_list:
        if not isinstance(run, VerificationEvidence):
            gaps.append(Gap("INVALID_VERIFICATION_EVIDENCE", None, "selected run is not validated evidence"))
        elif run.result != "PASS":
            gaps.append(Gap("VERIFICATION_FAILED", run.uid, "selected verification did not pass"))
    if gaps:
        return ConvergenceVerdict("BLOCKED", tuple(gaps), "structural, freshness, or verification gaps remain", stall_fingerprint(gaps))
    return ConvergenceVerdict("CONVERGED", (), "all deterministic conditions satisfied", "")


def append_convergence(path: str | Path, verdict: ConvergenceVerdict, *, work_uid: str, engine_version: str) -> None:
    """Append a historical convergence fact; never overwrite an earlier run."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"work_uid": work_uid, "verdict": verdict.verdict, "reason": verdict.reason, "fingerprint": verdict.fingerprint, "engine_version": engine_version}
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
