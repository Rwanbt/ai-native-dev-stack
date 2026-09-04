"""PR-07 read-only adapters; providers cannot mutate or decide convergence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ReadOnlyFinding:
    source: str
    code: str
    message: str
    severity: str = "WARN"


def collect_findings(*, graphify: Iterable[Mapping[str, Any]] = (), anti_debt: Iterable[Mapping[str, Any]] = ()) -> tuple[ReadOnlyFinding, ...]:
    findings: list[ReadOnlyFinding] = []
    for item in graphify:
        findings.append(ReadOnlyFinding("graphify", str(item.get("code", "GRAPH_FINDING")), str(item.get("message", "")), str(item.get("severity", "WARN"))))
    for item in anti_debt:
        findings.append(ReadOnlyFinding("anti-debt", str(item.get("code", "DEBT_FINDING")), str(item.get("message", "")), str(item.get("severity", "WARN"))))
    return tuple(findings)


def memory_summary(*, work_uid: str, problem: str, result: str, decisions: Iterable[str] = (), failures: Iterable[str] = (), verification_summary: str = "", refs: Iterable[str] = ()) -> dict[str, Any]:
    """Create a compact historical summary; it is never copied into the contract."""

    return {"work_uid": work_uid, "problem": problem, "result": result, "important_decisions": list(decisions), "important_failures": list(failures), "verification_summary": verification_summary, "refs": list(refs)}
