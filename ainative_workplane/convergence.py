"""PR-05 deterministic convergence decision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .traceability import Gap, TraceabilityResult


BLOCKING_FRESHNESS = frozenset({"STALE_CONTRACT", "STALE_SCOPE", "STALE_DEPENDENCY", "COMMAND_REGISTRY_CHANGED", "POLICY_CHANGED"})


@dataclass(frozen=True)
class ConvergenceVerdict:
    verdict: str
    gaps: tuple[Gap, ...]
    reason: str


def converge(traceability: TraceabilityResult, runs: Iterable[Mapping[str, Any]], *, freshness: Iterable[str] = ()) -> ConvergenceVerdict:
    gaps = list(traceability.gaps)
    states = set(freshness)
    for state in sorted(states & BLOCKING_FRESHNESS):
        gaps.append(Gap(state, None, "blocking freshness state"))
    run_list = list(runs)
    if not run_list:
        return ConvergenceVerdict("INVALID", tuple(gaps), "no verification run is available")
    for run in run_list:
        if run.get("status") not in {"PASS", "pass"}:
            gaps.append(Gap("VERIFICATION_FAILED", run.get("uid"), "selected verification did not pass"))
    if gaps:
        return ConvergenceVerdict("BLOCKED", tuple(gaps), "structural, freshness, or verification gaps remain")
    return ConvergenceVerdict("CONVERGED", (), "all deterministic conditions satisfied")
