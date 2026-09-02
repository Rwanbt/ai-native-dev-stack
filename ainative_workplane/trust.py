"""Fail-closed evaluation of V2 evidence authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .contracts import ContractError, canonical_digest, validate_artifact
from .evidence import VerificationEvidence


_TRUST_LEVEL = {
    "UNTRACKED": 0,
    "GIT_DIRTY": 0,
    "LOCAL_UNTRUSTED": 0,
    "GIT_RECORDED": 1,
    "GIT_REVIEWED": 2,
    "CI_APPROVED": 3,
    "SIGNED": 4,
}


@dataclass(frozen=True)
class TrustVerdict:
    trusted: bool
    code: str


def _without_digest(value: Any, digest_key: str) -> Any:
    if isinstance(value, Mapping):
        return {key: _without_digest(item, digest_key) for key, item in value.items() if key != digest_key}
    if isinstance(value, list):
        return [_without_digest(item, digest_key) for item in value]
    return value


def policy_commitment(policy: Mapping[str, Any]) -> str:
    """Return the stable policy commitment without self-referential digest fields."""

    return canonical_digest(_without_digest(policy, "policy_digest"))


def approval_root_commitment(root: Mapping[str, Any]) -> str:
    """Return the stable approval-root commitment without its self-reference."""

    return canonical_digest(_without_digest(root, "root_digest"))


def _policy_predicates_match(policy: Mapping[str, Any], commitment: str) -> bool:
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        predicate = policy.get(field)
        if not isinstance(predicate, Mapping) or predicate.get("policy_digest") != commitment:
            return False
    return True


def _valid_root_chain(root: Mapping[str, Any], *, policy_digest: str, required_level: int, approval_chain: Iterable[Mapping[str, Any]]) -> bool:
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
        if _TRUST_LEVEL[current["root_provenance"]] < required_level:
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
        current = parent


def evaluate_trust(evidence: VerificationEvidence, *, policy: Mapping[str, Any] | None, approval_root: Mapping[str, Any] | None, approval_chain: Iterable[Mapping[str, Any]] = (), governed: bool = True) -> TrustVerdict:
    """Reject missing, malformed, mismatched, or insufficient authority."""

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
    required = policy["verification_evidence_provenance"]
    if _TRUST_LEVEL[record["evidence_provenance"]] < _TRUST_LEVEL[required]:
        return TrustVerdict(False, "INSUFFICIENT_EVIDENCE_PROVENANCE")
    if not _valid_root_chain(approval_root, policy_digest=commitment, required_level=_TRUST_LEVEL[required], approval_chain=approval_chain):
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID")
    return TrustVerdict(True, "TRUSTED")
