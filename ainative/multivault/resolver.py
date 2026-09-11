"""Descriptive workspace resolver; it never grants a capability."""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
from .binding import (
    ALLOW_ROOT_FRESH,
    DENY_ROOT_IDENTITY_UNRECORDED,
    DENY_ROOT_MEASUREMENT_INCOMPLETE,
    DENY_ROOT_STALE,
    RootFreshnessVerdict,
    WorkspaceDeclaration,
    admit,
    root_freshness,
    trusted_classification,
)
from .authority_store import AuthorityStore
from .identity import measure_checkout_identity, measure_root_identity
from .schema import SecurityClassification


@dataclass(frozen=True)
class ResolvedSecurityContext:
    security_domain_id: str
    vault_logical_id: str
    checkout_identity: str
    authorized: bool
    classification: SecurityClassification | None
    root_freshness: RootFreshnessVerdict | None = None
    checkout_freshness: RootFreshnessVerdict | None = None


def resolve(declaration: WorkspaceDeclaration, store: AuthorityStore) -> ResolvedSecurityContext:
    authorized = admit(declaration, store)
    classification = trusted_classification(store.binding(declaration.security_domain_id)) if authorized else None
    return ResolvedSecurityContext(
        declaration.security_domain_id,
        declaration.vault_logical_id,
        declaration.checkout_identity,
        authorized,
        classification,
    )



ALLOW_CHECKOUT_FRESH = "ALLOW_CHECKOUT_FRESH"
DENY_CHECKOUT_IDENTITY_UNRECORDED = "DENY_CHECKOUT_IDENTITY_UNRECORDED"
DENY_CHECKOUT_MEASUREMENT_INCOMPLETE = "DENY_CHECKOUT_MEASUREMENT_INCOMPLETE"
DENY_CHECKOUT_STALE = "DENY_CHECKOUT_STALE"

_CHECKOUT_CODES = {
    ALLOW_ROOT_FRESH: ALLOW_CHECKOUT_FRESH,
    DENY_ROOT_IDENTITY_UNRECORDED: DENY_CHECKOUT_IDENTITY_UNRECORDED,
    DENY_ROOT_MEASUREMENT_INCOMPLETE: DENY_CHECKOUT_MEASUREMENT_INCOMPLETE,
    DENY_ROOT_STALE: DENY_CHECKOUT_STALE,
}


def _precise_checkout_verdict(verdict: RootFreshnessVerdict) -> RootFreshnessVerdict:
    """Shared comparison, checkout-precise diagnostics: no silent legacy fallback."""
    return replace(verdict, decision=_CHECKOUT_CODES.get(verdict.decision, verdict.decision))

def resolve_with_vault_root(
    declaration: WorkspaceDeclaration,
    store: AuthorityStore,
    vault_root: Path,
    checkout_root: Path | None = None,
) -> ResolvedSecurityContext:
    """Declaration admission plus operator-recorded vault root freshness.

    Fail closed: an unmeasured or stale root denies; measurement never
    escapes as an exception.
    """
    context = resolve(declaration, store)
    if not context.authorized:
        return context
    binding_record = store.binding(declaration.security_domain_id)
    measured = measure_root_identity(declaration.vault_logical_id, vault_root)
    verdict = root_freshness(binding_record, measured)
    checkout_measured = (
        measure_checkout_identity(checkout_root) if checkout_root is not None else None
    )
    checkout_verdict = _precise_checkout_verdict(
        root_freshness(binding_record, checkout_measured, field_name="checkout_identity")
    )
    authorized = (
        verdict.decision == ALLOW_ROOT_FRESH
        and checkout_verdict.decision == ALLOW_CHECKOUT_FRESH
    )
    return ResolvedSecurityContext(
        context.security_domain_id,
        context.vault_logical_id,
        context.checkout_identity,
        authorized=authorized,
        classification=context.classification,
        root_freshness=verdict,
        checkout_freshness=checkout_verdict,
    )
