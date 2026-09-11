"""Descriptive workspace resolver; it never grants a capability."""
from __future__ import annotations
from dataclasses import dataclass
from .binding import WorkspaceDeclaration, admit, trusted_classification
from .authority_store import AuthorityStore
from .schema import SecurityClassification


@dataclass(frozen=True)
class ResolvedSecurityContext:
    security_domain_id: str
    vault_logical_id: str
    checkout_identity: str
    authorized: bool
    classification: SecurityClassification | None


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