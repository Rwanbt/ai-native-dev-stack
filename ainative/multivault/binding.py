"""Non-authoritative workspace declaration compared to operator authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .authority_store import AuthorityStore
from .schema import SecurityClassification


@dataclass(frozen=True)
class WorkspaceDeclaration:
    security_domain_id: str
    vault_logical_id: str
    checkout_identity: str
    requested_classification: SecurityClassification = SecurityClassification.PERSONAL
    requested_roots: tuple[str, ...] = ()


def trusted_classification(binding: dict[str, Any] | None) -> SecurityClassification | None:
    """Return the operator-classified level; unknown values fail closed."""
    if not binding:
        return None
    try:
        return SecurityClassification[binding.get("classification", "PERSONAL")]
    except KeyError:
        return None


def admit(declaration: WorkspaceDeclaration, store: AuthorityStore) -> bool:
    """A copied or expanded repository declaration fails exact operator comparison."""
    binding = store.binding(declaration.security_domain_id)
    if not binding:
        return False
    if binding.get("vault") != declaration.vault_logical_id:
        return False
    if binding.get("checkout") != declaration.checkout_identity:
        return False
    trusted = trusted_classification(binding)
    if trusted is None or declaration.requested_classification > trusted:
        return False
    allowed_roots = set(binding.get("roots", []))
    if not set(declaration.requested_roots) <= allowed_roots:
        return False
    return True
ALLOW_ROOT_FRESH = "ALLOW_ROOT_FRESH"
DENY_BINDING_MISSING = "DENY_BINDING_MISSING"
DENY_ROOT_IDENTITY_UNRECORDED = "DENY_ROOT_IDENTITY_UNRECORDED"
DENY_ROOT_MEASUREMENT_INCOMPLETE = "DENY_ROOT_MEASUREMENT_INCOMPLETE"
DENY_ROOT_STALE = "DENY_ROOT_STALE"

ROOT_IDENTITY_FIELD = "root_identity"


@dataclass(frozen=True)
class RootFreshnessVerdict:
    decision: str
    recorded_root_identity: str | None = None
    measured_root_identity: str | None = None


def root_freshness(
    binding: dict[str, Any] | None,
    measured_root_identity: str | None,
    field_name: str = ROOT_IDENTITY_FIELD,
) -> RootFreshnessVerdict:
    """Compare the operator-recorded vault root identity to the measured one.

    Fail closed: an unrecorded identity or an absent measurement is never
    freshness. The measurement is injected - this module performs no I/O.
    """
    if not binding:
        return RootFreshnessVerdict(DENY_BINDING_MISSING)
    recorded = binding.get(field_name)
    if not recorded:
        return RootFreshnessVerdict(DENY_ROOT_IDENTITY_UNRECORDED)
    if not measured_root_identity:
        return RootFreshnessVerdict(
            DENY_ROOT_MEASUREMENT_INCOMPLETE,
            recorded_root_identity=recorded,
        )
    if measured_root_identity != recorded:
        return RootFreshnessVerdict(
            DENY_ROOT_STALE,
            recorded_root_identity=recorded,
            measured_root_identity=measured_root_identity,
        )
    return RootFreshnessVerdict(
        ALLOW_ROOT_FRESH,
        recorded_root_identity=recorded,
        measured_root_identity=measured_root_identity,
    )