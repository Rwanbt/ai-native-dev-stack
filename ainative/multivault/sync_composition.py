"""Sync composition root: loads existing owners, links them, propagates the verdict.

Pure wiring (decision A-prime): the approved remote, the transport policy and
the observed state are trusted operator/observer inputs injected by the
caller; this module constructs no policy object, validates nothing itself and
performs no Git call of its own - every transfer goes through the
GovernedTransferEngine, including for PERSONAL classifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .authority_store import AuthorityStore, AuthorityStoreCorruptError
from .binding import WorkspaceDeclaration
from .push_guard import GovernedPushAuthority
from .resolver import resolve_with_vault_root
from .transfer_engine import GovernedTransferEngine, PushPreparation, TransferOutcome


DENY_AUTHORITY_STORE_CORRUPT = "DENY_AUTHORITY_STORE_CORRUPT"
DENY_DECLARATION_NOT_ADMITTED = "DENY_DECLARATION_NOT_ADMITTED"


@dataclass(frozen=True)
class SyncRequest:
    """Operator-supplied sync inputs; every path and identity is explicit."""

    store_path: Path
    domain: str
    vault_logical_id: str
    checkout_identity: str
    vault_root: Path
    checkout_root: Path
    repository: Path


def _resolution_denial(context) -> str:
    if context.root_freshness is None and context.checkout_freshness is None:
        return DENY_DECLARATION_NOT_ADMITTED
    for verdict in (context.root_freshness, context.checkout_freshness):
        if verdict is not None and verdict.decision.startswith("DENY_"):
            return verdict.decision
    return DENY_DECLARATION_NOT_ADMITTED


def _authorized_context(request: SyncRequest):
    """Resolve before any engine exists; a denial never reaches Git."""
    try:
        store = AuthorityStore(request.store_path)
        declaration = WorkspaceDeclaration(
            security_domain_id=request.domain,
            vault_logical_id=request.vault_logical_id,
            checkout_identity=request.checkout_identity,
        )
        context = resolve_with_vault_root(
            declaration, store, request.vault_root, request.checkout_root
        )
    except (AuthorityStoreCorruptError, OSError):
        return None, TransferOutcome("DENY", DENY_AUTHORITY_STORE_CORRUPT, "authority store is unreadable")
    if not context.authorized:
        code = _resolution_denial(context)
        return None, TransferOutcome("DENY", code, "the workspace declaration is not authorized")
    return context, None


def _engine(request: SyncRequest, context, approved_remote: Any, transport_policy: Any, forbidden_paths) -> GovernedTransferEngine:
    return GovernedTransferEngine(
        request.repository,
        approved_remote=approved_remote,
        transport_policy=transport_policy,
        push_authority=GovernedPushAuthority(request.domain, request.checkout_identity),
        classification=context.classification,
        forbidden_paths=tuple(forbidden_paths),
    )


def compose_fetch(
    request: SyncRequest,
    *,
    approved_remote: Any,
    transport_policy: Any,
    observed_remote: Any,
    observed_transport: Any,
    requested_refs: tuple[str, ...],
    verified_at: str,
    forbidden_paths: tuple[str, ...] = (),
) -> TransferOutcome:
    """Authorized domain, approved remote/transport state, then the engine fetch."""
    context, denial = _authorized_context(request)
    if denial is not None:
        return denial
    engine = _engine(request, context, approved_remote, transport_policy, forbidden_paths)
    return engine.fetch(
        requested_refs=tuple(requested_refs),
        observed_remote=observed_remote,
        observed_transport=observed_transport,
        verified_at=verified_at,
    )


def compose_push(
    request: SyncRequest,
    *,
    approved_remote: Any,
    transport_policy: Any,
    observed_remote: Any,
    observed_transport: Any,
    source_oid: str,
    expected_remote_base_oid: str,
    target_ref: str,
    exact_refspec: str,
    expected_git_identity: str,
    forbidden_paths: tuple[str, ...] = (),
) -> TransferOutcome:
    """Authorized domain, approved remote/transport state, then the engine push."""
    context, denial = _authorized_context(request)
    if denial is not None:
        return denial
    engine = _engine(request, context, approved_remote, transport_policy, forbidden_paths)
    preparation = engine.begin_push(
        source_oid=source_oid,
        expected_remote_base_oid=expected_remote_base_oid,
        target_ref=target_ref,
        exact_refspec=exact_refspec,
        observed_remote=observed_remote,
        observed_transport=observed_transport,
        expected_git_identity=expected_git_identity,
    )
    if isinstance(preparation, TransferOutcome):
        return preparation
    return preparation.execute()
