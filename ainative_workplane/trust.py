"""Fail-closed evaluation of V2 evidence authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .contracts import ContractError, canonical_digest, validate_artifact
from .evidence import VerificationEvidence
from .predicates import predicate_refusal


# The numeric ladder is gone. It made SIGNED satisfy a policy that asked for
# CI, because 4 >= 3, which is false about the world. Authority is now decided
# by observed facts (see provenance.py), and the strings artifacts carry are
# descriptive only.


@dataclass(frozen=True)
class TrustVerdict:
    trusted: bool
    code: str


def unmet(facts: Any, required: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the required facts an observation does not support.

    @contract Absent an observation, nothing is established: every required
    fact is reported unmet rather than assumed.
    """

    if facts is None:
        return tuple(sorted(name for name, needed in required.items() if needed))
    return facts.unmet(required)


def _without_digest(value: Any, digest_key: str) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_digest(item, digest_key) for key, item in value.items() if key != digest_key}
    if isinstance(value, list):
        return [_without_digest(item, digest_key) for item in value]
    return value


def policy_commitment(policy: Mapping[str, Any]) -> str:
    """Return the stable policy commitment without self-referential digest fields."""

    return canonical_digest(_without_digest(policy, "policy_digest"))


def successor_commitment(root: Mapping[str, Any]) -> str:
    """Digest the candidate successor's content, without self-reference.

    WHY: an approval that names only a UID approves a name, not a state. The
    successor's contents could then change while keeping both the UID and the
    approval that points at it.
    """

    stripped = _without_digest(root, "root_digest")
    approval = stripped.get("transition_approval")
    if isinstance(approval, Mapping):
        stripped = {**stripped, "transition_approval": {key: item for key, item in approval.items() if key != "successor_commitment"}}
    return canonical_digest(stripped)


def approval_root_commitment(root: Mapping[str, Any]) -> str:
    """Return the stable approval-root commitment without its self-reference."""

    return canonical_digest(_without_digest(root, "root_digest"))


def _policy_predicates_match(policy: Mapping[str, Any], commitment: str) -> bool:
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        predicate = policy.get(field)
        if not isinstance(predicate, Mapping) or predicate.get("policy_digest") != commitment:
            return False
    return True


def _authorized_transition(successor: Mapping[str, Any], parent: Mapping[str, Any], *, predicate_id: str, policy_digest: str, required: Mapping[str, Any], facts: Any) -> bool:
    """Check that the predecessor's authority accepted this exact successor.

    WHY this is separate from the predecessor link: a successor pointing at a
    predecessor proves lineage, not consent. Without this, anyone able to
    write a new root could name the trusted one as its parent and inherit its
    authority.
    """

    approval = successor.get("transition_approval")
    if not isinstance(approval, Mapping):
        return False
    if approval.get("predicate_id") != predicate_id or approval.get("policy_digest") != policy_digest:
        return False
    if approval.get("successor_uid") != successor.get("uid"):
        return False
    if approval.get("successor_commitment") != successor_commitment(successor):
        return False
    if approval.get("predecessor_digest") != parent.get("root_digest"):
        return False
    # A rotation is a change of authority, so it clears the same bar as any
    # other one: the predicate the policy configures, actually satisfied.
    if predicate_refusal(predicate_id, facts) is not None:
        return False
    return not unmet(facts, required)


def _valid_root_chain(root: Mapping[str, Any], *, policy_digest: str, required: Mapping[str, Any], approval_chain: Iterable[Mapping[str, Any]], facts: Any = None, predicate_id: str = "") -> bool:
    roots: dict[str, Mapping[str, Any]] = {root["uid"]: root}
    try:
        for candidate in approval_chain:
            validate_artifact(candidate)
            roots[candidate["uid"]] = candidate
    except (ContractError, KeyError, TypeError):
        return False
    current = root
    seen: set[str] = set()
    while True:
        uid = current["uid"]
        if uid in seen or current.get("policy_digest") != policy_digest:
            return False
        if current.get("root_digest") != approval_root_commitment(current):
            return False
        if unmet(facts, required):
            return False
        seen.add(uid)
        predecessor = current.get("predecessor")
        if predecessor is None:
            return True
        if not isinstance(predecessor, Mapping):
            return False
        parent = roots.get(predecessor.get("uid"))
        if parent is None or predecessor.get("digest") != parent.get("root_digest"):
            return False
        if not _authorized_transition(current, parent, predicate_id=predicate_id, policy_digest=policy_digest, required=required, facts=facts):
            return False
        current = parent


def evaluate_trust(evidence: VerificationEvidence, *, policy: Mapping[str, Any] | None, approval_root: Mapping[str, Any] | None, approval_chain: Iterable[Mapping[str, Any]] = (), governed: bool = True, evidence_facts: Any = None, authority_facts: Any = None) -> TrustVerdict:
    """Reject missing, malformed, mismatched, or insufficient authority.

    @contract Authority comes from facts observed about the objects
    themselves — the checkout for evidence, the artifact's own location for the
    approval root — never from a provenance string an artifact carries about
    itself.
    """

    if policy is None or approval_root is None:
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID" if governed else "LOCAL_UNTRUSTED")
    try:
        validate_artifact(policy)
        validate_artifact(approval_root)
    except ContractError:
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID")
    record = evidence.artifact
    commitment = policy_commitment(policy)
    if not _policy_predicates_match(policy, commitment):
        return TrustVerdict(False, "POLICY_COMMITMENT_INVALID")
    root = record["approval_root"]
    if root["uid"] != approval_root["uid"] or root["digest"] != approval_root["root_digest"]:
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID")
    if record["policy_digest"] != commitment or approval_root["policy_digest"] != commitment:
        return TrustVerdict(False, "POLICY_CHANGED")
    if unmet(evidence_facts, policy["required_evidence_facts"]):
        return TrustVerdict(False, "INSUFFICIENT_EVIDENCE_PROVENANCE")
    if not _valid_root_chain(approval_root, policy_digest=commitment, required=policy["required_mutation_facts"], approval_chain=approval_chain, facts=authority_facts, predicate_id=policy["approval_predicate"]["predicate_id"]):
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID")
    return TrustVerdict(True, "TRUSTED")
