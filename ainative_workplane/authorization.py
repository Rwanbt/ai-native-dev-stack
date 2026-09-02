"""Authorized suppression of convergence gaps by waivers and human approvals.

A waiver or a human approval only carries authority when the policy in force
configured the predicate it claims, its provenance clears the policy bar, and
its policy commitment still matches. Anything else is recorded as a rejection
rather than silently ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .contracts import ContractError, validate_artifact
from .traceability import Gap
from .trust import TRUST_LEVELS, policy_commitment


# A waiver may hide unfinished work; it may never hide the fact that the
# engine could not establish authority in the first place.
UNWAIVABLE = frozenset({
    "FRESHNESS_UNAVAILABLE",
    "ROOT_OF_TRUST_INVALID",
    "POLICY_COMMITMENT_INVALID",
    "INVALID_VERIFICATION_EVIDENCE",
    "UNRELATED_VERIFICATION_EVIDENCE",
})

_EFFECTIVE = "effective"


def _uid_of(record: Any) -> str | None:
    return record.get("uid") if isinstance(record, Mapping) and isinstance(record.get("uid"), str) else None


def _target_uid(record: Mapping[str, Any]) -> str | None:
    target = record.get("target")
    return target.get("uid") if isinstance(target, Mapping) else None


def _expired(record: Mapping[str, Any], now: datetime) -> bool:
    raw = record.get("expires_at")
    if raw is None:
        return False
    if not isinstance(raw, str):
        raise ContractError("INVALID_FIELD", "expires_at must be a timestamp string")
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("INVALID_FIELD", "expires_at is not an ISO timestamp") from error
    if moment.tzinfo is None:
        raise ContractError("INVALID_FIELD", "expires_at must carry a timezone")
    return moment <= now


def _rejection(record: Mapping[str, Any], policy: Mapping[str, Any], commitment: str, rule_field: str) -> str | None:
    """Return why the record lacks authority, or None when it holds."""

    if record.get("policy_digest") != commitment:
        return "policy commitment does not match the policy in force"
    rule = policy[rule_field]
    predicate = record.get("approval_predicate")
    if not isinstance(predicate, Mapping):
        return "no approval predicate is declared"
    if predicate.get("predicate_id") != rule["predicate_id"] or predicate.get("policy_digest") != commitment:
        return "approval predicate is not the one the policy configures"
    required = policy["success_condition_mutation_provenance"]
    if TRUST_LEVELS[record["approval_provenance"]] < TRUST_LEVELS[required]:
        return "approval provenance is below the policy requirement"
    return None


def _classify(record: Any, policy: Mapping[str, Any] | None, commitment: str, rule_field: str, kind: str, now: datetime) -> tuple[Mapping[str, Any] | None, Gap | None]:
    """Return the record when it may act, otherwise the gap explaining why not."""

    uid = _uid_of(record)
    try:
        validate_artifact(record)
        expired = _expired(record, now)
    except ContractError as error:
        return None, Gap(f"INVALID_{kind}", uid, f"{kind.lower()} artifact is invalid: {error.code}")
    if policy is None:
        return None, Gap(f"UNAUTHORIZED_{kind}", uid, f"{kind.lower()} claims authority with no policy in force")
    if kind == "WAIVER" and record.get("state") != _EFFECTIVE:
        return None, Gap("WAIVER_NOT_EFFECTIVE", uid, f"waiver state is {record.get('state')!r}, not effective")
    if expired:
        return None, Gap(f"{kind}_EXPIRED", uid, f"{kind.lower()} expired before this evaluation")
    reason = _rejection(record, policy, commitment, rule_field)
    if reason is not None:
        return None, Gap(f"UNAUTHORIZED_{kind}", uid, reason)
    return record, None


def apply_authorizations(gaps: Iterable[Gap], *, policy: Mapping[str, Any] | None = None, waivers: Iterable[Mapping[str, Any]] = (), human_approvals: Iterable[Mapping[str, Any]] = (), now: datetime | None = None) -> list[Gap]:
    """Remove the gaps a valid, authorized waiver or approval covers.

    @contract Every supplied artifact either suppresses exactly the gap it
    targets or contributes its own rejection gap. Nothing is discarded.
    """

    remaining = list(gaps)
    waiver_list = list(waivers)
    approval_list = list(human_approvals)
    if not waiver_list and not approval_list:
        return remaining
    moment = now or datetime.now(timezone.utc)
    commitment = policy_commitment(policy) if policy is not None else ""
    rejections: list[Gap] = []
    effective_waivers: list[Mapping[str, Any]] = []
    effective_approvals: list[Mapping[str, Any]] = []
    for record in waiver_list:
        accepted, rejected = _classify(record, policy, commitment, "waiver_approval_rule", "WAIVER", moment)
        if accepted is None:
            rejections.append(rejected)
        else:
            effective_waivers.append(accepted)
    for record in approval_list:
        accepted, rejected = _classify(record, policy, commitment, "human_approval_rule", "HUMAN_APPROVAL", moment)
        if accepted is None:
            rejections.append(rejected)
        else:
            effective_approvals.append(accepted)
    kept = [gap for gap in remaining if not _covered(gap, effective_waivers, effective_approvals)]
    return kept + rejections


def _covered(gap: Gap, waivers: list[Mapping[str, Any]], approvals: list[Mapping[str, Any]]) -> bool:
    if gap.code in UNWAIVABLE:
        return False
    for waiver in waivers:
        if _target_uid(waiver) == gap.uid and waiver.get("scope") == gap.code:
            return True
    if gap.code != "UNVERIFIED_SPECIFICATION":
        return False
    return any(_target_uid(approval) == gap.uid for approval in approvals)
