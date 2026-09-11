"""Fail-closed, domain-bound admission for local REST operations.

This module does not make HTTP calls.  A transport adapter may be added only after
MV-00 supplies a qualifying endpoint/vault-correlation probe for its exact tuple.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from .runtime_authority import RuntimeAuthority, RuntimeContextHandle


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


@dataclass(frozen=True)
class RestEndpoint:
    url: str

    def normalized_url(self) -> str | None:
        try:
            parsed = urlparse(self.url)
        except ValueError:
            return None
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.hostname.lower() not in _LOOPBACK_HOSTS:
            return None
        if parsed.username or parsed.password or parsed.fragment or parsed.query:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        if port is None:
            return None
        path = parsed.path or "/"
        return f"{parsed.scheme}://{parsed.hostname.lower()}:{port}{path}"


@dataclass(frozen=True)
class EndpointCorrelation:
    """Trusted result from an exact versioned probe; URL equality is insufficient."""

    security_domain_id: str
    vault_identity: str
    endpoint: RestEndpoint
    probe_evidence_digest: str
    correlated: bool

    def eligible(self) -> bool:
        return bool(
            self.security_domain_id
            and self.vault_identity
            and self.endpoint.normalized_url()
            and self.probe_evidence_digest
            and self.correlated
        )


@dataclass(frozen=True)
class RestCredential:
    """Secret capability material deliberately redacted from normal output."""

    _value: str = field(repr=False, compare=False)

    def __str__(self) -> str:
        return "<redacted>"

    def __repr__(self) -> str:
        return "RestCredential(<redacted>)"


class DomainRestBroker:
    """Admits a REST operation only for its issuing authority and correlated vault."""

    def __init__(self, correlation: EndpointCorrelation, credential: RestCredential):
        self._correlation = correlation
        self._credential = credential

    def authorize(
        self,
        authority: RuntimeAuthority,
        handle: RuntimeContextHandle,
        caller_identity: str,
        endpoint: RestEndpoint,
    ) -> RestCredential | None:
        """Return the scoped credential only to a transport owned by this broker."""
        state = authority.resolve(handle, caller_identity)
        if state is None or not self._correlation.eligible():
            return None
        if state.security_domain_id != self._correlation.security_domain_id:
            return None
        if state.vault_identity != self._correlation.vault_identity:
            return None
        expected = self._correlation.endpoint.normalized_url()
        if expected is None or endpoint.normalized_url() != expected:
            return None
        return self._credential
