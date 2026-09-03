"""The authoritative production entrypoint.

`converge()` is a pure kernel: it decides from whatever traceability, trust and
freshness objects it is handed. That makes it testable and makes it the wrong
thing to expose to a caller, because a caller who supplies the inputs decides
the verdict.

This module is the boundary. It takes a work directory and a checkout, and
derives every input itself:

    committed manifest → validated artifacts → contract, policy, root,
    specifications, registry → observed provenance → per-evidence trust,
    freshness and binding → eligible evidence only → pure convergence

Nothing here accepts a contract, a policy, a root, a registry, a trust verdict
or a freshness result from the caller. An agent that wants a different answer
has to change committed state through the controller, where the change is
visible.

It also re-reads the authority after the verifications have run. A
registered command has a filesystem, and nothing stops it from rewriting the
manifest, the policy or the registry while it executes; a verdict computed from
objects loaded before that would be a verdict about state that no longer
exists.

Nor does it accept evidence. A schema-valid `verification_run` proves shape,
not origin: every digest in it can be read from committed state and from the
checkout, so a file written by hand is indistinguishable from one a runner
produced. Against a local actor with write access there is no signature that
actor could not also produce, so the boundary does not try to authenticate
recorded files — it executes the declared verifications itself and judges only
what it just produced. Recorded runs are a local execution log, not an audit
trail: nothing authenticates them and anyone who can write the directory can
write one. They are never an input to a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .bootstrap import BootstrapError, admits, governs, read_creation_approval, verified_anchor
from .contracts import canonical_digest, canonical_path
from .controller import ControllerError, WorkController
from .convergence import BLOCKING_FRESHNESS, ConvergenceVerdict, converge
from .evidence import EvidenceError, VerificationEvidence
from .freshness import FreshnessResult, evaluate_checkout_freshness
from .provenance import ProvenanceFacts, blob_at_commit, observe, observe_artifacts, observe_commit, repository_location
from .runner import RunnerError, VerificationRunner
from .snapshot import SnapshotError, build_repository_snapshot, snapshot_reference
from .traceability import Gap, analyze
from .trust import TrustVerdict, approval_root_commitment, evaluate_trust, policy_commitment

# Artifacts whose content defines what success means. The contract digest is
# taken over exactly these, so changing any of them invalidates evidence bound
# to the previous state.
SUCCESS_CONDITION = ("requirements", "acceptance_criteria", "tasks", "verification_specifications", "waivers")


@dataclass(frozen=True)
class EvidenceAssessment:
    """Why one verification run may or may not support convergence."""

    evidence_uid: str
    verification_spec_uid: str
    schema_valid: bool
    binding_valid: bool
    trust: TrustVerdict | None
    freshness: FreshnessResult | None
    substance_eligible: bool
    relationship_valid: bool
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class WorkEvaluation:
    verdict: ConvergenceVerdict
    assessments: tuple[EvidenceAssessment, ...]
    contract_digest: str
    provenance: ProvenanceFacts
    authority_provenance: ProvenanceFacts


class EvaluationError(RuntimeError):
    """Authoritative state could not be established at all."""


def read_recorded_runs(directory: str | Path) -> list[Mapping[str, Any]]:
    """Read the audit trail. Never authority — see the module docstring."""

    return _load_evidence(Path(directory))


def _load_evidence(directory: Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise EvaluationError(f"UNREADABLE_EVIDENCE:{path.name}") from error
    return records


def _ineligible(record: Any, reason: str) -> EvidenceAssessment:
    uid = record.get("uid") if isinstance(record, Mapping) else None
    return EvidenceAssessment(str(uid), "", False, False, None, None, False, False, False, (reason,))


def _binding_reasons(artifact: Mapping[str, Any], *, spec_digest: str | None, contract_digest: str, registry_digest: str | None, policy_digest: str | None, root_reference: Mapping[str, str] | None, work_uid: str | None = None, revision: int | None = None) -> list[str]:
    reasons: list[str] = []
    if work_uid is not None and artifact["work"]["uid"] != work_uid:
        reasons.append("UNRELATED_WORK")
    if revision is not None and artifact["contract_revision"] != revision:
        reasons.append("STALE_CONTRACT_REVISION")
    if spec_digest is None:
        reasons.append("UNRELATED_VERIFICATION_EVIDENCE")
    elif artifact["verification_specification"]["digest"] != spec_digest:
        reasons.append("VERIFICATION_SPEC_CHANGED")
    if artifact["contract_digest"] != contract_digest:
        reasons.append("STALE_CONTRACT")
    if registry_digest is None or artifact["command_registry_digest"] != registry_digest:
        reasons.append("COMMAND_REGISTRY_CHANGED")
    if policy_digest is None or artifact["policy_digest"] != policy_digest:
        reasons.append("POLICY_CHANGED")
    if root_reference is None or artifact["approval_root"] != root_reference:
        reasons.append("ROOT_OF_TRUST_CHANGED")
    return reasons


def _assess(record: Any, *, specifications: Mapping[str, Mapping[str, Any]], spec_digests: Mapping[str, str], authority: Mapping[str, Any], repository_root: str | Path, observation: ProvenanceFacts, authority_observation: ProvenanceFacts, relationship_gaps: frozenset[str]) -> EvidenceAssessment:
    """Qualify one run on its own, never by inheritance from another."""

    try:
        evidence = VerificationEvidence(record)
    except EvidenceError as error:
        return _ineligible(record, f"INVALID_VERIFICATION_EVIDENCE:{error}")
    artifact = evidence.artifact
    spec_uid = evidence.verification_specification_uid
    binding = _binding_reasons(
        artifact,
        spec_digest=spec_digests.get(spec_uid),
        contract_digest=authority["contract_digest"],
        registry_digest=authority["registry_digest"],
        policy_digest=authority["policy_digest"],
        root_reference=authority["root_reference"],
        work_uid=authority["work_uid"],
        revision=authority["revision"],
    )
    reasons = list(binding)
    trust = evaluate_trust(evidence, policy=authority["policy"], approval_root=authority["approval_root"], approval_chain=authority["root_history"], policy_chain=authority["policy_history"], evidence_facts=observation, authority_facts=authority_observation, genesis_digest=authority["genesis_root_digest"], transition_facts=authority["transition_facts"])
    if not trust.trusted:
        reasons.append(trust.code)
    freshness = _freshness(evidence, specifications.get(spec_uid), repository_root=repository_root, authority=authority, spec_digest=spec_digests.get(spec_uid))
    if freshness is None:
        reasons.append("FRESHNESS_UNAVAILABLE")
    else:
        reasons.extend(sorted(set(freshness.states) & BLOCKING_FRESHNESS))
    substance_eligible = artifact["result"] != "SUSPICIOUS_VERIFICATION"
    if not substance_eligible:
        reasons.append("SUSPICIOUS_VERIFICATION")
    relationship_valid = spec_uid not in relationship_gaps
    if not relationship_valid:
        reasons.append("INVALID_VERIFICATION_RELATIONSHIP")
    if artifact["result"] != "PASS":
        reasons.append("VERIFICATION_FAILED")
    return EvidenceAssessment(
        evidence_uid=evidence.uid,
        verification_spec_uid=spec_uid,
        schema_valid=True,
        binding_valid=not binding,
        trust=trust,
        freshness=freshness,
        substance_eligible=substance_eligible,
        relationship_valid=relationship_valid,
        eligible=not reasons,
        reasons=tuple(reasons),
    )


def _freshness(evidence: VerificationEvidence, specification: Mapping[str, Any] | None, *, repository_root: str | Path, authority: Mapping[str, Any], spec_digest: str | None) -> FreshnessResult | None:
    """Recompute freshness from the checkout, never from a supplied fixture."""

    if specification is None or authority["registry_digest"] is None or authority["policy_digest"] is None or authority["root_reference"] is None:
        return None
    try:
        return evaluate_checkout_freshness(
            evidence,
            repository_root=str(repository_root),
            scope=specification.get("execution_scope", []),
            dependency_paths=specification.get("covered_implementation_paths", []),
            current_contract_digest=authority["contract_digest"],
            current_registry_digest=authority["registry_digest"],
            current_policy_digest=authority["policy_digest"],
            current_approval_root=authority["root_reference"],
            current_specification_digest=spec_digest,
        )
    except (SnapshotError, OSError, KeyError):
        return None


def _authority_paths(work_dir: str | Path, manifest: Mapping[str, Any]) -> list[Path]:
    """The files that carry authority: the manifest and the artifacts it points at.

    Deliberately not the whole work directory. The run log lives there too, and
    a fresh audit entry must not make the rules look tampered with.
    """

    root = Path(work_dir)
    paths = [root / "manifest.json"]
    for name, pointer in manifest["artifacts"].items():
        if pointer.get("normative"):
            paths.append(root / canonical_path(pointer["path"]))
    return paths


def _authority_commitment(authority: Mapping[str, Any], artifacts: Mapping[str, Any]) -> str:
    """One digest over everything a verdict depends on."""

    return canonical_digest({
        "manifest": authority["manifest"],
        "artifacts": {name: value for name, value in sorted(artifacts.items())},
    })


def _authority_drift(work_dir: str | Path, before: str) -> list[Gap]:
    """Detect authority that moved while the verifications were running."""

    try:
        artifacts, authority, _ = _authority(work_dir)
    except EvaluationError as error:
        return [Gap("AUTHORITY_CHANGED_DURING_EVALUATION", None, f"authority became unreadable during evaluation: {error}")]
    if _authority_commitment(authority, artifacts) != before:
        return [Gap("AUTHORITY_CHANGED_DURING_EVALUATION", None, "the committed authority changed while the verifications ran")]
    return []


def _execute_declared_verifications(work_dir: str | Path, repository_root: str | Path, specifications: Mapping[str, Mapping[str, Any]]) -> tuple[list[VerificationEvidence], list[Gap]]:
    """Run every executable declared verification, now.

    WHY here rather than reading recorded runs: a recorded run is a file, and
    a file is whatever its author wrote. Producing the evidence is the only
    local way to know where it came from.
    """

    produced: list[VerificationEvidence] = []
    gaps: list[Gap] = []
    for uid in sorted(specifications):
        if specifications[uid].get("relationship") == "human_approval":
            continue
        try:
            produced.append(run_verification(work_dir, repository_root, uid))
        except (EvaluationError, RunnerError, SnapshotError, OSError) as error:
            gaps.append(Gap("VERIFICATION_NOT_EXECUTABLE", uid, f"{type(error).__name__}: {error}"))
    return produced, gaps


def _project_trust_gaps(work_dir: str | Path, authority: Mapping[str, Any]) -> list[Gap]:
    """Refuse to converge on a work that is its own root of trust.

    WHY here and not only in the controller: creating a work directory is a
    local act, and a local act must not be able to decide what a project
    trusts. The controller refuses a *new* work that contradicts an existing
    anchor; this refuses a *verdict* for any work the project never pinned. The
    anchor is measured the way every other authority artifact is -- by
    observing the object, against the predicate it declares for itself.
    """

    anchor = authority["anchor"]
    if anchor is None:
        refused = authority["anchor_error"]
        if refused is None:
            return [Gap("PROJECT_TRUST_UNINITIALIZED", None, "the project has no trust anchor, so this work is governed only by rules it declared for itself")]
        code = "PROJECT_TRUST_UNVERIFIED" if refused.startswith("PROJECT_TRUST_UNVERIFIED") else "PROJECT_TRUST_INVALID"
        return [Gap(code, None, refused)]
    refusal = governs(anchor, approval_root=authority["approval_root"], root_history=authority["root_history"])
    if refusal is not None:
        return [Gap("PROJECT_TRUST_MISMATCH", None, refusal)]
    # Which root governs this work is one question; who admitted *this* initial
    # contract is another. Revision 1 states what must be accomplished, so
    # leaving it to whoever created the directory leaves the success conditions
    # to the party they constrain.
    approval, facts = read_creation_approval(work_dir, anchor)
    genesis = authority["genesis_digest"]
    if genesis is None:
        return [Gap("PROJECT_TRUST_INVALID", None, "the work's genesis revision could not be read, so nothing can be compared with its creation approval")]
    admission = admits(anchor, approval=approval, genesis_digest=genesis, facts=facts)
    if admission is not None:
        return [Gap("WORK_NOT_ADMITTED", None, admission)]
    return []


def evaluate_work(work_dir: str | Path, repository_root: str | Path) -> WorkEvaluation:
    """Decide convergence for a governed work directory against a checkout.

    @contract Every input is derived from committed state and from the
    checkout. No contract, policy, root, registry, trust verdict, freshness
    result or evidence is accepted from the caller: the declared verifications
    are executed here, and only their results are judged.
    @contract The work must be one the project already pinned. A work whose
    authority nothing above it established is unevaluable, however internally
    consistent it is.
    """

    artifacts, authority, specifications = _authority(work_dir)
    policy = authority["policy"]
    approval_root = authority["approval_root"]
    registry = authority["registry"]
    spec_digests = {uid: canonical_digest(spec) for uid, spec in specifications.items()}

    graph = analyze(artifacts.get("requirements", []), artifacts.get("acceptance_criteria", []), artifacts.get("tasks", []), list(specifications.values()))
    relationship_gaps = frozenset(gap.uid for gap in graph.gaps if gap.code in {"INVALID_VERIFICATION_RELATIONSHIP", "HUMAN_APPROVAL_WITHOUT_PREDICATE"} and gap.uid)

    scope: list[str] = []
    for specification in specifications.values():
        scope.extend(specification.get("execution_scope", []))
        scope.extend(specification.get("covered_implementation_paths", []))
    # Two domains, deliberately not one: what the checkout supports about the
    # code under verification, and what is established about the work
    # directory holding the rules, the root and the exceptions. A clean
    # checkout says nothing about a work directory living somewhere else.
    signers = authority["anchor"]["authorized_signers"] if authority["anchor"] else None
    observation = observe(repository_root, scope, authorized_signers=signers)
    authority_observation = observe_artifacts(_authority_paths(work_dir, authority["manifest"]), authorized_signers=signers)

    before = _authority_commitment(authority, artifacts)
    produced, execution_gaps = _execute_declared_verifications(work_dir, repository_root, specifications)
    execution_gaps.extend(_authority_drift(work_dir, before))
    assessments = tuple(
        _assess(evidence.artifact, specifications=specifications, spec_digests=spec_digests, authority=authority, repository_root=repository_root, observation=observation, authority_observation=authority_observation, relationship_gaps=relationship_gaps)
        for evidence in produced
    )
    eligible = [evidence for evidence, assessment in zip(produced, assessments) if assessment.eligible]
    rejected = tuple(Gap("INELIGIBLE_VERIFICATION_EVIDENCE", assessment.evidence_uid, "; ".join(assessment.reasons)) for assessment in assessments if not assessment.eligible) + tuple(execution_gaps) + tuple(_project_trust_gaps(work_dir, authority))

    # Trust and freshness were established per evidence above; what remains for
    # the kernel is whether the authority documents exist at all.
    authority_present = policy is not None and approval_root is not None and registry is not None
    machine_specs = frozenset(uid for uid, specification in specifications.items() if specification.get("relationship") != "human_approval")
    verdict = converge(
        replace(graph, gaps=graph.gaps + rejected),
        eligible,
        machine_specs=machine_specs,
        freshness=FreshnessResult(frozenset()) if authority_present else None,
        trust=TrustVerdict(True, "AUTHORITY_PRESENT") if authority_present else None,
        policy=policy,
        waivers=artifacts.get("waivers", []),
        human_approvals=artifacts.get("human_approvals", []),
        authorization_facts=authority_observation,
    )
    return WorkEvaluation(verdict=verdict, assessments=assessments, contract_digest=authority["contract_digest"], provenance=observation, authority_provenance=authority_observation)


def _transition_facts(work_dir: str | Path, transitions: Mapping[str, Mapping[str, Any]], anchor: Mapping[str, Any] | None) -> dict[str, ProvenanceFacts]:
    """Re-establish, per transition, what authorized it when it happened.

    Three things have to line up, and the seventh round only checked the first:

    - the commit exists and carries the required provenance;
    - that commit actually contained an approval at the recorded path;
    - that approval canonicalizes to the recorded digest.

    A commit signature alone says something was signed, not what. Reading the
    object back out of the commit is what binds the transition to the approval
    the manifest claims authorized it. Any step failing leaves the transition
    with no entry at all, and an unbound transition is invalid.
    """

    located = repository_location(work_dir)
    if located is None:
        return {}
    repository, _ = located
    signers = anchor["authorized_signers"] if anchor else None
    facts: dict[str, ProvenanceFacts] = {}
    for uid, evidence in transitions.items():
        recorded = blob_at_commit(repository, evidence["commit"], evidence["approval_path"])
        if recorded is None:
            continue
        try:
            approved = json.loads(recorded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if canonical_digest(approved) != evidence["approval_digest"]:
            continue
        facts[uid] = observe_commit(repository, evidence["commit"], authorized_signers=signers)
    return facts


def _authority(work_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Mapping[str, Any]]]:
    """Load committed state and the identities derived from it."""

    controller = WorkController(work_dir)
    try:
        manifest, artifacts = controller.load_committed_artifacts()
    except ControllerError as error:
        raise EvaluationError(f"NO_AUTHORITATIVE_STATE:{error}") from error
    policy = artifacts.get("project_policy")
    approval_root = artifacts.get("approval_root")
    registry = artifacts.get("command_registry")
    history = controller.root_history()
    anchor_path: Path | None = None
    anchor: dict[str, Any] | None = None
    anchor_error: str | None = None
    try:
        located = verified_anchor(work_dir)
        if located is not None:
            anchor_path, anchor = located
    except BootstrapError as error:
        anchor_error = str(error)
    specifications = {spec["uid"]: spec for spec in artifacts.get("verification_specifications", [])}
    authority = {
        "policy": policy,
        "approval_root": approval_root,
        "registry": registry,
        "contract_digest": canonical_digest({name: artifacts.get(name, []) for name in SUCCESS_CONDITION}),
        "registry_digest": canonical_digest(registry) if registry is not None else None,
        "policy_digest": policy_commitment(policy) if policy is not None else None,
        "root_reference": {"uid": approval_root["uid"], "digest": approval_root["root_digest"]} if approval_root is not None else None,
        "work_uid": manifest["work_uid"],
        "revision": manifest["revision"],
        "manifest": manifest,
        "root_history": history,
        "policy_history": controller.policy_history(),
        "transition_facts": _transition_facts(work_dir, controller.root_transitions(), anchor),
        "genesis_digest": controller.genesis_normative_digest(),
        "genesis_root_digest": approval_root_commitment(history[0]) if history else None,
        "anchor_path": anchor_path,
        "anchor": anchor,
        "anchor_error": anchor_error,
    }
    return artifacts, authority, specifications


def run_verification(work_dir: str | Path, repository_root: str | Path, specification_uid: str) -> VerificationEvidence:
    """Execute one committed verification and record bound evidence.

    @contract The binding is built from committed authority and from the
    checkout, and the recorded provenance is what was observed, not what the
    caller would like it to be. A caller cannot hand in a binding.
    """

    artifacts, authority, specifications = _authority(work_dir)
    specification = specifications.get(specification_uid)
    if specification is None:
        raise EvaluationError(f"UNKNOWN_VERIFICATION_SPECIFICATION:{specification_uid}")
    if authority["registry"] is None or authority["policy_digest"] is None or authority["root_reference"] is None:
        raise EvaluationError("INCOMPLETE_AUTHORITY")
    command = specification.get("command")
    if not isinstance(command, str) or not command:
        raise EvaluationError("SPECIFICATION_DECLARES_NO_COMMAND")
    scope = list(specification.get("execution_scope", []))
    dependencies = list(specification.get("covered_implementation_paths", []))
    observation = observe(repository_root, scope + dependencies)
    facts = observation.to_record()
    snapshot = build_repository_snapshot(
        repository_root,
        scope=scope,
        dependency_paths=dependencies,
        command_registry_digest=authority["registry_digest"],
        policy_digest=authority["policy_digest"],
    )
    binding = {
        "work": {"uid": authority["work_uid"], "digest": authority["contract_digest"]},
        "contract_revision": authority["revision"],
        "contract_digest": authority["contract_digest"],
        "verification_specification": {"uid": specification_uid, "digest": canonical_digest(specification)},
        "command_registry_digest": authority["registry_digest"],
        "policy_digest": authority["policy_digest"],
        "approval_root": authority["root_reference"],
        "repository_snapshot": snapshot_reference(snapshot),
        "snapshot_content_digest": snapshot["content_digest"],
        "snapshot_dependency_digest": snapshot["dependency_digest"],
        "snapshot_head": snapshot["head"],
        "producer": "ainative-workplane",
        "producer_version": __import__("ainative_workplane").__version__,
        "evidence_provenance": "GIT_RECORDED" if facts["git_recorded"] else "GIT_DIRTY",
    }
    runner = VerificationRunner(authority["registry"], runs_dir=Path(work_dir) / "runs")
    return runner.run(command, cwd=repository_root, binding=binding, require_substance=True)
