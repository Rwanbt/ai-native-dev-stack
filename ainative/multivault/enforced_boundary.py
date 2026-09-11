"""ENFORCED execution-boundary evidence: canonical SID identity and ACL policy checks.

This module is read-only observation. It never grants capability: it records
whether the physical boundary properties hold for a workload principal and
produces the ExecutionBoundaryDigest the external authenticator reports.
"""
from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Mapping

from .schema import digest as canonical_digest

WORKLOAD_PRINCIPAL_NAME = "ainative-enforced"

OBSERVATION_EVENT = "event"
OBSERVATION_POLL = "poll"
OBSERVATION_PER_OPERATION = "per_operation"

ACL_DENIED = "ACL_DENIED"
ACL_GRANTED = "ACL_GRANTED"
ACL_UNREADABLE = "ACL_UNREADABLE"

BOUNDARY_VALID = "BOUNDARY_VALID"
BOUNDARY_REVOKED = "BOUNDARY_REVOKED"


@dataclass(frozen=True)
class BoundaryEvidence:
    property_name: str
    source: str
    observation_mode: str
    verified_at: float
    max_age_seconds: float
    measurement_digest: str

    def is_fresh(self, now: float) -> bool:
        return (now - self.verified_at) <= self.max_age_seconds


@dataclass(frozen=True)
class BoundaryVerdict:
    decision: str
    reasons: tuple[str, ...]
    execution_boundary_digest: str


def resolve_principal_sid(name: str) -> str | None:
    """Canonical identity: the real SID, never the display name."""
    try:
        script = (
            f"(New-Object System.Security.Principal.NTAccount('{name}')).Translate("
            "[System.Security.Principal.SecurityIdentifier]).Value"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, encoding="utf-8", errors="replace", check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    sid = (result.stdout or "").strip()
    return sid if result.returncode == 0 and sid else None


def evaluate_acl_for_sid(path: str, sid: str) -> str:
    """Return ACL_DENIED only on a positive deny; unreadable stays unreadable."""
    try:
        result = subprocess.run(
            ["icacls", path], capture_output=True, encoding="utf-8", errors="replace", check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ACL_UNREADABLE
    if result.returncode != 0:
        return ACL_UNREADABLE
    lowered = (result.stdout or "").lower()
    if sid.lower() in lowered and "(deny)" in lowered:
        return ACL_DENIED
    if sid.lower() in lowered:
        return ACL_GRANTED
    return ACL_DENIED  # absent for this SID means no access path is granted here


def boundary_digest(evidence: tuple[BoundaryEvidence, ...]) -> str:
    return canonical_digest({
        item.property_name: {
            "source": item.source,
            "mode": item.observation_mode,
            "digest": item.measurement_digest,
        }
        for item in sorted(evidence, key=lambda entry: entry.property_name)
    })


def verify_boundary(
    evidence: tuple[BoundaryEvidence, ...],
    required_properties: Mapping[str, float],
    *,
    now: float,
) -> BoundaryVerdict:
    """Fail closed: every required property must be present and fresh."""
    reasons: list[str] = []
    by_name = {item.property_name: item for item in evidence}
    for property_name, max_age in required_properties.items():
        item = by_name.get(property_name)
        if item is None:
            reasons.append(f"{property_name}: evidence missing")
            continue
        if item.max_age_seconds > max_age:
            reasons.append(f"{property_name}: declared max_age exceeds policy")
            continue
        if not item.is_fresh(now):
            reasons.append(f"{property_name}: evidence is stale")
    if reasons:
        return BoundaryVerdict(BOUNDARY_REVOKED, tuple(reasons), boundary_digest(evidence))
    return BoundaryVerdict(BOUNDARY_VALID, (), boundary_digest(evidence))