"""PR-03 deterministic traceability and structural gap detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .contracts import ContractError, validate_artifact


@dataclass(frozen=True)
class Gap:
    code: str
    uid: str | None
    detail: str


@dataclass(frozen=True)
class TraceabilityResult:
    requirement_count: int
    requirement_to_acceptance: tuple[tuple[str, str], ...]
    acceptance_to_verification: tuple[tuple[str, str], ...]
    requirement_to_task: tuple[tuple[str, str], ...]
    gaps: tuple[Gap, ...]

    @property
    def is_structurally_valid(self) -> bool:
        return not self.gaps


def _uid(item: Mapping[str, Any]) -> str:
    value = item.get("uid")
    if not isinstance(value, str) or not value:
        raise ContractError("INVALID_UID", "traceability artifact uid must be non-empty")
    return value


def _refs(item: Mapping[str, Any], field: str) -> tuple[str, ...]:
    values = item.get(field, [])
    if not isinstance(values, list):
        raise ContractError("INVALID_FIELD", f"{field} must be an array")
    result: list[str] = []
    for reference in values:
        if not isinstance(reference, Mapping) or not isinstance(reference.get("uid"), str):
            raise ContractError("BROKEN_REFERENCE", f"{field} contains a malformed reference")
        result.append(reference["uid"])
    return tuple(result)


def _index(items: Iterable[Mapping[str, Any]], kind: str) -> tuple[dict[str, Mapping[str, Any]], list[Gap]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    gaps: list[Gap] = []
    for item in items:
        uid = _uid(item)
        if uid in indexed:
            gaps.append(Gap("DUPLICATE_UID", uid, f"duplicate {kind} UID"))
        indexed[uid] = item
    return indexed, gaps


def analyze(requirements: Iterable[Mapping[str, Any]], acceptance_criteria: Iterable[Mapping[str, Any]], tasks: Iterable[Mapping[str, Any]], verification_specs: Iterable[Mapping[str, Any]]) -> TraceabilityResult:
    """Build only structural edges; no prose or LLM output affects the result."""

    reqs, gaps = _index(requirements, "requirement")
    acs, ac_gaps = _index(acceptance_criteria, "acceptance criterion")
    task_map, task_gaps = _index(tasks, "task")
    specs, spec_gaps = _index(verification_specs, "verification specification")
    gaps.extend(ac_gaps + task_gaps + spec_gaps)
    req_ac: list[tuple[str, str]] = []
    ac_verify: list[tuple[str, str]] = []
    req_task: list[tuple[str, str]] = []
    ac_incoming: set[str] = set()
    task_incoming: set[str] = set()
    spec_incoming: set[str] = set()
    verified_requirements: set[str] = set()
    for uid, requirement in reqs.items():
        acceptance_refs = _refs(requirement, "acceptance_criteria")
        if not acceptance_refs:
            gaps.append(Gap("REQ_WITHOUT_ACCEPTANCE", uid, "requirement has no acceptance criterion"))
        for ac_uid in acceptance_refs:
            req_ac.append((uid, ac_uid))
            ac_incoming.add(ac_uid)
            if ac_uid not in acs:
                gaps.append(Gap("BROKEN_REFERENCE", uid, f"acceptance criterion {ac_uid} does not exist"))
    for uid, criterion in acs.items():
        requirement = criterion.get("requirement")
        if not isinstance(requirement, Mapping) or requirement.get("uid") not in reqs:
            gaps.append(Gap("BROKEN_REFERENCE", uid, "criterion requirement reference does not exist"))
        verify_refs = _refs(criterion, "verification_specifications")
        if not verify_refs:
            gaps.append(Gap("UNVERIFIABLE_ACCEPTANCE", uid, "acceptance criterion has no verification specification"))
        else:
            requirement_ref = criterion.get("requirement")
            if isinstance(requirement_ref, Mapping) and isinstance(requirement_ref.get("uid"), str):
                verified_requirements.add(requirement_ref["uid"])
        for spec_uid in verify_refs:
            ac_verify.append((uid, spec_uid))
            spec_incoming.add(spec_uid)
            if spec_uid not in specs:
                gaps.append(Gap("BROKEN_REFERENCE", uid, f"verification specification {spec_uid} does not exist"))
    for uid, task in task_map.items():
        req_refs = _refs(task, "requirements")
        if not req_refs:
            gaps.append(Gap("TASK_WITHOUT_REQ", uid, "task has no requirement reference"))
        for req_uid in req_refs:
            req_task.append((req_uid, uid))
            task_incoming.add(req_uid)
            if req_uid not in reqs:
                gaps.append(Gap("BROKEN_REFERENCE", uid, f"requirement {req_uid} does not exist"))
        if req_refs and not any(req_uid in verified_requirements for req_uid in req_refs):
            gaps.append(Gap("TASK_WITHOUT_VERIFICATION", uid, "task has no requirement with verification"))
    for req_uid in reqs:
        if req_uid not in task_incoming:
            gaps.append(Gap("REQ_WITHOUT_TASK", req_uid, "requirement has no task"))
    for ac_uid in acs:
        if ac_uid not in ac_incoming:
            gaps.append(Gap("BROKEN_REFERENCE", ac_uid, "acceptance criterion is not linked from its requirement"))
    for spec_uid in specs:
        if spec_uid not in spec_incoming:
            gaps.append(Gap("ORPHAN_VERIFICATION_SPEC", spec_uid, "verification specification is not linked from an acceptance criterion"))
    return TraceabilityResult(len(reqs), tuple(req_ac), tuple(ac_verify), tuple(req_task), tuple(gaps))
