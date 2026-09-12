"""Fail-closed in-memory runtime capability authority for Multi-Vault.

This is deliberately a local authority primitive, not a process-isolation claim.
It issues no handle until its caller supplies a fully qualified Phase-B result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import secrets
from threading import Lock

from .schema import AllowedContextEnvelope, SecurityEpoch


@dataclass(frozen=True)
class ImmutableAuthoritativeSecurityState:
    """The immutable state a valid handle resolves to inside one authority."""

    security_domain_id: str
    security_epoch: SecurityEpoch
    vault_identity: str
    checkout_identity: str
    project_security_id: str
    classification: str
    allowed_context_envelope: AllowedContextEnvelope
    approved_model_egress_digest: str
    memory_policy_digest: str
    persistence_assurance_digest: str
    execution_profile: str
    runtime_observation_policy_digest: str
    authority_instance_id: str


@dataclass(frozen=True)
class SensitiveQualification:
    """Trusted Phase-B input; any missing proof denies handle issuance."""

    model_egress_verified: bool = False
    session_containment_verified: bool = False
    carried_state_revalidated: bool = False

    @property
    def eligible(self) -> bool:
        return (
            self.model_egress_verified
            and self.session_containment_verified
            and self.carried_state_revalidated
        )


@dataclass(frozen=True)
class RuntimeContextHandle:
    """Opaque, non-persistent capability; normal representations never reveal it."""

    authority_instance_id: str
    security_domain_id: str
    security_epoch_digest: str
    _secret: str = field(repr=False, compare=False)

    def __str__(self) -> str:
        return "<redacted>"

    def __repr__(self) -> str:
        return "RuntimeContextHandle(<redacted>)"


@dataclass(frozen=True)
class Revocation:
    reason: str
    security_epoch_digest: str


@dataclass(frozen=True)
class _IssuedHandle:
    caller_identity: str
    security_epoch_digest: str


class RuntimeAuthority:
    """Owns handles for exactly one domain and one authority instance."""

    def __init__(self, state: ImmutableAuthoritativeSecurityState):
        if not state.security_domain_id or not state.authority_instance_id:
            raise ValueError("runtime authority requires domain and instance identities")
        if state.security_domain_id != state.security_epoch.security_domain_id:
            raise ValueError("security epoch belongs to another domain")
        self._state = state
        self._issued: dict[str, _IssuedHandle] = {}
        self._lock = Lock()

    @property
    def state(self) -> ImmutableAuthoritativeSecurityState:
        return self._state

    def issue_phase_b_handle(
        self, caller_identity: str, qualification: SensitiveQualification
    ) -> RuntimeContextHandle | None:
        """Issue only after all required Phase-B security proofs are present."""
        if not caller_identity or not qualification.eligible:
            return None
        secret = secrets.token_urlsafe(32)
        epoch_digest = self._state.security_epoch.digest()
        with self._lock:
            self._issued[secret] = _IssuedHandle(caller_identity, epoch_digest)
        return RuntimeContextHandle(
            authority_instance_id=self._state.authority_instance_id,
            security_domain_id=self._state.security_domain_id,
            security_epoch_digest=epoch_digest,
            _secret=secret,
        )

    def resolve(
        self, handle: RuntimeContextHandle, caller_identity: str
    ) -> ImmutableAuthoritativeSecurityState | None:
        """Return state only for the issuing authority, current epoch and caller."""
        if not caller_identity or handle.authority_instance_id != self._state.authority_instance_id:
            return None
        if handle.security_domain_id != self._state.security_domain_id:
            return None
        current_epoch = self._state.security_epoch.digest()
        if handle.security_epoch_digest != current_epoch:
            return None
        with self._lock:
            issued = self._issued.get(handle._secret)
        if issued is None or issued.caller_identity != caller_identity:
            return None
        if issued.security_epoch_digest != current_epoch:
            return None
        return self._state

    def revoke(self, handle: RuntimeContextHandle, reason: str) -> Revocation:
        """Revocation is idempotent and returns no capability material."""
        with self._lock:
            self._issued.pop(handle._secret, None)
        return Revocation(reason=reason, security_epoch_digest=self._state.security_epoch.digest())

    def revoke_all(self, reason: str) -> Revocation:
        """Use after drift or supervisor loss; all current handles become invalid."""
        with self._lock:
            self._issued.clear()
        return Revocation(reason=reason, security_epoch_digest=self._state.security_epoch.digest())


def authority_from_operator_state(
    *,
    security_domain_id: str,
    vault_identity: str,
    checkout_identity: str,
    project_security_id: str,
    classification: str,
    allowed_context_envelope: AllowedContextEnvelope,
    security_epoch: SecurityEpoch,
    approved_model_egress_digest: str,
    memory_policy_digest: str,
    persistence_assurance_digest: str,
    execution_profile: str,
    runtime_observation_policy_digest: str,
    authority_instance_id: str | None = None,
) -> RuntimeAuthority:
    """Materialize the runtime authority from operator-authoritative values.

    Pure materialization: it reads no repository content, decides no
    classification and invents no digest; an incomplete operator state fails
    closed instead of being completed here.
    """
    authoritative = (
        security_domain_id,
        vault_identity,
        checkout_identity,
        project_security_id,
        classification,
        approved_model_egress_digest,
        memory_policy_digest,
        persistence_assurance_digest,
        execution_profile,
        runtime_observation_policy_digest,
    )
    if not all(authoritative):
        raise ValueError("every authoritative identity and digest is required")
    return RuntimeAuthority(
        ImmutableAuthoritativeSecurityState(
            security_domain_id=security_domain_id,
            security_epoch=security_epoch,
            vault_identity=vault_identity,
            checkout_identity=checkout_identity,
            project_security_id=project_security_id,
            classification=classification,
            allowed_context_envelope=allowed_context_envelope,
            approved_model_egress_digest=approved_model_egress_digest,
            memory_policy_digest=memory_policy_digest,
            persistence_assurance_digest=persistence_assurance_digest,
            execution_profile=execution_profile,
            runtime_observation_policy_digest=runtime_observation_policy_digest,
            authority_instance_id=authority_instance_id or secrets.token_urlsafe(16),
        )
    )
