"""Non-authoritative workspace declaration compared to operator authority."""
from __future__ import annotations
from dataclasses import dataclass
from .authority_store import AuthorityStore

@dataclass(frozen=True)
class WorkspaceDeclaration:
    security_domain_id: str
    vault_logical_id: str
    checkout_identity: str

def admit(declaration: WorkspaceDeclaration, store: AuthorityStore) -> bool:
    """A copied or expanded repository declaration fails exact operator comparison."""
    binding=store.binding(declaration.security_domain_id)
    if not binding: return False
    return binding.get("vault") == declaration.vault_logical_id and binding.get("checkout") == declaration.checkout_identity
