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