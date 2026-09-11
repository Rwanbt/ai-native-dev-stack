"""Descriptive workspace resolver; it never grants a capability."""
from __future__ import annotations
from dataclasses import dataclass
from .binding import WorkspaceDeclaration, admit
from .authority_store import AuthorityStore

@dataclass(frozen=True)
class ResolvedSecurityContext:
    security_domain_id: str
    vault_logical_id: str
    checkout_identity: str
    authorized: bool

def resolve(declaration: WorkspaceDeclaration, store: AuthorityStore) -> ResolvedSecurityContext:
    return ResolvedSecurityContext(declaration.security_domain_id, declaration.vault_logical_id, declaration.checkout_identity, admit(declaration, store))
