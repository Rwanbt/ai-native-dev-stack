"""Descriptive workspace resolver; it never grants a capability."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .binding import (
    ALLOW_ROOT_FRESH,
    RootFreshnessVerdict,
    WorkspaceDeclaration,
    admit,
    root_freshness,
    trusted_classification,
)
from .authority_store import AuthorityStore
from .identity import measure_root_identity
from .schema import SecurityClassification


@dataclass(frozen=True)
class ResolvedSecurityContext:
    security_domain_id: str
    vault_logical_id: str
    checkout_identity: str
    authorized: bool
    classification: SecurityClassification | None
    root_freshness: RootFreshnessVerdict | None = None


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


def resolve_with_vault_root(
    declaration: WorkspaceDeclaration,
    store: AuthorityStore,
    vault_root: Path,
) -> ResolvedSecurityContext:
    """Declaration admission plus operator-recorded vault root freshness.

    Fail closed: an unmeasured or stale root denies; measurement never
    escapes as an exception.
    """
    context = resolve(declaration, store)
    if not context.authorized:
        return context
    measured = measure_root_identity(declaration.vault_logical_id, vault_root)
    verdict = root_freshness(store.binding(declaration.security_domain_id), measured)
    return ResolvedSecurityContext(
        context.security_domain_id,
        context.vault_logical_id,
        context.checkout_identity,
        authorized=verdict.decision == ALLOW_ROOT_FRESH,
        classification=context.classification,
        root_freshness=verdict,
    )
