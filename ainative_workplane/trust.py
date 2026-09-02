"""Fail-closed evaluation of V2 evidence authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ContractError, validate_artifact
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


def evaluate_trust(evidence: VerificationEvidence, *, policy: Mapping[str, Any] | None, approval_root: Mapping[str, Any] | None, governed: bool = True) -> TrustVerdict:
    """Reject missing, malformed, mismatched, or insufficient authority."""

    if policy is None or approval_root is None:
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID" if governed else "LOCAL_UNTRUSTED")
    try:
        validate_artifact(policy)
        validate_artifact(approval_root)
    except ContractError:
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID")
    record = evidence.artifact
    root = record["approval_root"]
    if root["uid"] != approval_root["uid"] or root["digest"] != approval_root["root_digest"]:
        return TrustVerdict(False, "ROOT_OF_TRUST_INVALID")
    if record["policy_digest"] != approval_root.get("policy_digest", record["policy_digest"]):
        return TrustVerdict(False, "POLICY_CHANGED")
    required = policy["verification_evidence_provenance"]
    if _TRUST_LEVEL[record["evidence_provenance"]] < _TRUST_LEVEL[required]:
        return TrustVerdict(False, "INSUFFICIENT_EVIDENCE_PROVENANCE")
    if _TRUST_LEVEL[approval_root["root_provenance"]] < _TRUST_LEVEL[required]:
        return TrustVerdict(False, "INSUFFICIENT_ROOT_PROVENANCE")
    return TrustVerdict(True, "TRUSTED")
