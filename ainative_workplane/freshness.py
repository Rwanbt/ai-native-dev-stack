"""Deterministic freshness evaluation for bound verification evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .evidence import VerificationEvidence
from .snapshot import build_repository_snapshot, snapshot_reference


@dataclass(frozen=True)
class FreshnessResult:
    states: frozenset[str]


def evaluate_freshness(evidence: VerificationEvidence, *, current_contract_digest: str, current_snapshot: Mapping[str, Any], current_registry_digest: str, current_policy_digest: str, current_approval_root: Mapping[str, Any], current_specification_digest: str | None = None, current_head: str | None = None) -> FreshnessResult:
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
    if current_specification_digest is not None and record["verification_specification"]["digest"] != current_specification_digest:
        states.add("VERIFICATION_SPEC_CHANGED")
    # A commit that touches nothing in scope or in the dependency set is
    # information, not a reason to invalidate evidence.
    if current_head is not None and record["snapshot_head"] != current_head:
        states.add("STALE_REPO")
    prior_snapshot = record["repository_snapshot"]
    if prior_snapshot["uid"] != current_snapshot.get("uid") or prior_snapshot["digest"] != current_snapshot.get("digest"):
        states.add("STALE_SCOPE")
    return FreshnessResult(frozenset(states))


def evaluate_checkout_freshness(
    evidence: VerificationEvidence,
    *,
    repository_root: str,
    scope: Iterable[str],
    dependency_paths: Iterable[str],
    current_contract_digest: str,
    current_registry_digest: str,
    current_policy_digest: str,
    current_approval_root: Mapping[str, Any],
    current_specification_digest: str | None = None,
) -> FreshnessResult:
    """Recompute the evidence snapshot from the checkout before deciding freshness."""

    previous = evidence.artifact["repository_snapshot"]
    current = build_repository_snapshot(
        repository_root,
        scope=scope,
        dependency_paths=dependency_paths,
        command_registry_digest=current_registry_digest,
        policy_digest=current_policy_digest,
        uid=previous["uid"],
    )
    baseline = evaluate_freshness(
        evidence,
        current_contract_digest=current_contract_digest,
        current_snapshot=previous,
        current_registry_digest=current_registry_digest,
        current_policy_digest=current_policy_digest,
        current_approval_root=current_approval_root,
        current_specification_digest=current_specification_digest,
        current_head=current["head"],
    )
    states = set(baseline.states)
    if evidence.artifact["snapshot_content_digest"] != current["content_digest"]:
        states.add("STALE_SCOPE")
    if evidence.artifact["snapshot_dependency_digest"] != current["dependency_digest"]:
        states.add("STALE_DEPENDENCY")
    return FreshnessResult(frozenset(states))
