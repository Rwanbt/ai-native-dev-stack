"""Deterministic freshness evaluation for bound verification evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .evidence import VerificationEvidence


@dataclass(frozen=True)
class FreshnessResult:
    states: frozenset[str]


def evaluate_freshness(evidence: VerificationEvidence, *, current_contract_digest: str, current_snapshot: Mapping[str, Any], current_registry_digest: str, current_policy_digest: str, current_approval_root: Mapping[str, Any]) -> FreshnessResult:
    """Compare current normative identities without interpreting narrative state."""

    record = evidence.artifact
    states: set[str] = set()
    if record["contract_digest"] != current_contract_digest:
        states.add("STALE_CONTRACT")
    if record["command_registry_digest"] != current_registry_digest:
        states.add("COMMAND_REGISTRY_CHANGED")
    if record["policy_digest"] != current_policy_digest:
        states.add("POLICY_CHANGED")
    if record["approval_root"] != current_approval_root:
        states.add("ROOT_OF_TRUST_CHANGED")
    prior_snapshot = record["repository_snapshot"]
    if prior_snapshot["uid"] != current_snapshot.get("uid") or prior_snapshot["digest"] != current_snapshot.get("digest"):
        states.add("STALE_SCOPE")
    return FreshnessResult(frozenset(states))
