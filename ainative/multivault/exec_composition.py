"""Exec composition root: loads existing owners, links them, propagates the verdict.

Pure wiring (decision A-prime): this module constructs no authoritative object
and makes no classification decision. The runtime authority and the allowed
context envelope are materialized by their owners from operator-authoritative
values, the harness measurement by the harness adapter from real probe
evidence, and the launcher is injected. This module only sequences the owners:
store -> declaration -> live root measurements -> resolver -> immediate denial
-> repository admission -> execute_sensitive (gate A/B -> launcher).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .admission import admit_repository, scan_repository
from .authority_store import AuthorityStore, AuthorityStoreCorruptError
from .binding import WorkspaceDeclaration
from .exec_wrapper import ExecOutcome, execute_sensitive, positive_child_environment
from .resolver import resolve_with_vault_root


DENY_AUTHORITY_STORE_CORRUPT = "DENY_AUTHORITY_STORE_CORRUPT"
DENY_DECLARATION_NOT_ADMITTED = "DENY_DECLARATION_NOT_ADMITTED"
DENY_REPOSITORY_ADMISSION = "DENY_REPOSITORY_ADMISSION"


@dataclass(frozen=True)
class ExecRequest:
    """Operator-supplied exec inputs; every path and identity is explicit."""

    store_path: Path
    domain: str
    vault_logical_id: str
    checkout_identity: str
    vault_root: Path
    checkout_root: Path
    workspace: Path
    argv: tuple[str, ...]
    approved_env: Mapping[str, str] = field(default_factory=dict)
    required_os_env: Mapping[str, str] = field(default_factory=dict)
    requested_roots: tuple[str, ...] = ()


def _denial_code(context) -> str:
    if context.root_freshness is None and context.checkout_freshness is None:
        return DENY_DECLARATION_NOT_ADMITTED
    for verdict in (context.root_freshness, context.checkout_freshness):
        if verdict is not None and verdict.decision.startswith("DENY_"):
            return verdict.decision
    return DENY_DECLARATION_NOT_ADMITTED


def compose_exec(
    request: ExecRequest,
    *,
    authority: Any,
    envelope: Any,
    measure: Callable[[], Mapping[str, str]],
    spawn: Callable[..., Any],
    repository_adapter: Any = None,
    launcher_alive: Callable[[], bool] | None = None,
    authority_alive: Callable[[], bool] | None = None,
) -> ExecOutcome:
    """Store -> freshness -> admission -> frozen gate -> injected launcher.

    Any denial returns before the gate; the gate denial returns before the
    launcher; the launcher receives the exact objects the gate released and is
    invoked once - this module contains no retry path.
    """
    try:
        store = AuthorityStore(request.store_path)
        declaration = WorkspaceDeclaration(
            security_domain_id=request.domain,
            vault_logical_id=request.vault_logical_id,
            checkout_identity=request.checkout_identity,
            requested_roots=request.requested_roots,
        )
        context = resolve_with_vault_root(
            declaration, store, request.vault_root, request.checkout_root
        )
    except (AuthorityStoreCorruptError, OSError):
        return ExecOutcome(
            decision=DENY_AUTHORITY_STORE_CORRUPT,
            denial_code=DENY_AUTHORITY_STORE_CORRUPT,
            spawned=False,
        )
    if not context.authorized:
        code = _denial_code(context)
        return ExecOutcome(decision=code, denial_code=code, spawned=False)
    admission = admit_repository(
        scan_repository(request.checkout_root), repository_adapter, context.classification
    )
    if admission.decision != "ALLOW":
        return ExecOutcome(
            decision=DENY_REPOSITORY_ADMISSION,
            denial_code=DENY_REPOSITORY_ADMISSION,
            denial_detail=admission.reason,
            spawned=False,
        )
    child_env = positive_child_environment(request.approved_env, request.required_os_env)
    return execute_sensitive(
        workspace=request.workspace,
        security_domain_id=request.domain,
        checkout_identity=request.checkout_identity,
        authority=authority,
        envelope=envelope,
        argv=request.argv,
        base_env=child_env,
        measure=measure,
        spawn=spawn,
        launcher_alive=launcher_alive,
        authority_alive=authority_alive,
    )
