"""Thin, session-bound MCP projection adapter (ADR-0015 sections 1-2).

Transport-agnostic admission core only: the ephemeral endpoint and the opaque
session capability are per session and never reused; every response path is
revalidated through ResultConfinement before return. The adapter owns no
context selection and no vault authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import secrets
import time
from typing import Callable

from .confinement import ResultConfinement, within_roots
from .runtime_authority import RuntimeAuthority, RuntimeContextHandle


class McpOperation(str, Enum):
    VAULT_READ = "vault.read"
    VAULT_SEARCH = "vault.search"
    VAULT_WRITE = "vault.write"
    MEMORY_QUERY = "memory.query"
    GRAPH_QUERY = "graph.query"


@dataclass(frozen=True)
class SessionCapability:
    """Opaque per-session capability; normal representations never reveal it."""

    _value: str = field(repr=False, compare=False)

    def __str__(self) -> str:
        return "<redacted>"

    def __repr__(self) -> str:
        return "SessionCapability(<redacted>)"


@dataclass(frozen=True)
class McpResponse:
    decision: str
    reason: str


class ThinMcpAdapter:
    """One adapter per launcher, security domain and RuntimeContextHandle lineage."""

    def __init__(
        self,
        *,
        launcher_identity: str,
        security_domain_id: str,
        authority: RuntimeAuthority,
        handle: RuntimeContextHandle,
        confinement: ResultConfinement,
        allowed_write_targets: tuple[str, ...] = (),
        ttl_seconds: int = 3600,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not launcher_identity or not security_domain_id:
            raise ValueError("thin MCP adapter requires launcher and security domain identities")
        if ttl_seconds <= 0:
            raise ValueError("session capability requires a positive lifetime")
        self._launcher_identity = launcher_identity
        self._security_domain_id = security_domain_id
        self._authority = authority
        self._handle = handle
        self._confinement = confinement
        self._allowed_write_targets = tuple(allowed_write_targets)
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._started_at = clock()
        self._capability = SessionCapability(secrets.token_urlsafe(32))
        self._endpoint_id = secrets.token_urlsafe(16)
        self._closed = False

    @property
    def endpoint_id(self) -> str:
        return self._endpoint_id

    def session_capability(self) -> SessionCapability:
        """Hand the capability to the owning launcher exactly once."""
        return self._capability

    def close(self) -> None:
        self._closed = True

    def request(
        self,
        *,
        capability: SessionCapability,
        caller_identity: str,
        operation: McpOperation,
        result_paths: tuple[str, ...] = (),
    ) -> McpResponse:
        if self._closed:
            return McpResponse("DENY", "session is closed")
        if self._clock() - self._started_at > self._ttl_seconds:
            return McpResponse("DENY", "session capability expired")
        if (
            not isinstance(capability, SessionCapability)
            or not isinstance(capability._value, str)
            or not secrets.compare_digest(capability._value, self._capability._value)
        ):
            return McpResponse("DENY", "session capability is missing or foreign")
        if caller_identity != self._launcher_identity:
            return McpResponse("DENY", "foreign caller identity")
        state = self._authority.resolve(self._handle, caller_identity)
        if state is None:
            return McpResponse("DENY", "authority handle is foreign, expired or revoked")
        if state.security_domain_id != self._security_domain_id:
            return McpResponse("DENY", "authority state belongs to another security domain")
        if not isinstance(operation, McpOperation):
            return McpResponse("DENY", "unknown MCP operation")
        if operation is McpOperation.VAULT_WRITE:
            return self._validate_write(result_paths)
        return self._validate_results(state.project_security_id, result_paths)

    def _validate_write(self, result_paths: tuple[str, ...]) -> McpResponse:
        if len(result_paths) != 1:
            return McpResponse("DENY", "vault.write requires exactly one target path")
        target = result_paths[0]
        if not within_roots(self._allowed_write_targets, target):
            return McpResponse("DENY", "write target is outside the allowed write targets")
        if not self._confinement.vault_confine(target):
            return McpResponse("DENY", "write target is outside the VaultProtocol confinement")
        return McpResponse("ALLOW", "write target confined to the allowed targets and VaultProtocol")

    def _validate_results(self, project_security_id: str, result_paths: tuple[str, ...]) -> McpResponse:
        for path in result_paths:
            outcome = self._confinement.admit(path, project_security_id)
            if outcome.decision != "ALLOW":
                return McpResponse("DENY", outcome.reason)
        return McpResponse("ALLOW", f"{len(result_paths)} result path(s) revalidated")