"""PR-03 deterministic traceability and structural gap detection."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Iterable, Mapping

from .contracts import RELATIONSHIP_MODES, ContractError, validate_artifact


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


def _covers(patterns: Iterable[str], path: str) -> bool:
    """Match a declared coverage pattern against one implementation path."""

    for pattern in patterns:
        if pattern == path or fnmatchcase(path, pattern):
            return True
        prefix = pattern[:-3] if pattern.endswith("/**") else None
        if prefix is not None and (path == prefix or path.startswith(prefix + "/")):
            return True
    return False


def _scope_gaps(specs: Mapping[str, Mapping[str, Any]], spec_requirements: Mapping[str, set[str]], requirement_paths: Mapping[str, tuple[str, ...]]) -> list[Gap]:
    """Check each specification against the coverage its relationship demands."""

    gaps: list[Gap] = []
    for uid, spec in specs.items():
        relationship = spec.get("relationship")
        if relationship not in RELATIONSHIP_MODES:
            gaps.append(Gap("INVALID_VERIFICATION_RELATIONSHIP", uid, "verification relationship is missing or outside the closed enum"))
            continue
        covered = tuple(spec.get("covered_implementation_paths") or ())
        dependencies = tuple(spec.get("dependencies") or ())
        if relationship == "human_approval":
            if not isinstance(spec.get("approval_predicate"), Mapping):
                gaps.append(Gap("HUMAN_APPROVAL_WITHOUT_PREDICATE", uid, "human approval verification declares no mechanically checkable predicate"))
            continue
        if relationship == "external_artifact" and not dependencies:
            gaps.append(Gap("INSUFFICIENT_VERIFICATION_SCOPE", uid, "external artifact verification declares no provenance dependencies"))
            continue
        if relationship == "black_box" and not covered and not dependencies:
            gaps.append(Gap("INSUFFICIENT_VERIFICATION_SCOPE", uid, "black box verification declares neither covered paths nor dependencies"))
            continue
        if relationship != "direct_scope":
            continue
        expected: list[str] = []
        for requirement_uid in sorted(spec_requirements.get(uid, ())):
            expected.extend(requirement_paths.get(requirement_uid, ()))
        if not covered and expected:
            gaps.append(Gap("INSUFFICIENT_VERIFICATION_SCOPE", uid, "direct verification declares no covered implementation paths"))
            continue
        for path in sorted(set(expected)):
            if not _covers(covered, path):
                gaps.append(Gap("INSUFFICIENT_VERIFICATION_SCOPE", uid, f"implementation path {path} is not covered by this verification"))
                break
    return gaps


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
    spec_requirements: dict[str, set[str]] = {}
    for criterion_uid, spec_uid in ac_verify:
        requirement_ref = acs[criterion_uid].get("requirement")
        if isinstance(requirement_ref, Mapping) and isinstance(requirement_ref.get("uid"), str):
            spec_requirements.setdefault(spec_uid, set()).add(requirement_ref["uid"])
    requirement_paths: dict[str, tuple[str, ...]] = {}
    for uid, task in task_map.items():
        paths = tuple(task.get("implementation_paths") or ())
        for req_uid in _refs(task, "requirements"):
            requirement_paths[req_uid] = requirement_paths.get(req_uid, ()) + paths
    gaps.extend(_scope_gaps(specs, spec_requirements, requirement_paths))
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
