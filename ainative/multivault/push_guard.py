"""Governed push guard admission core (ADR-0016 sections 16-19).

The pre-push hook verifies a single-use capability bound to one exact
PushIntent. A direct or forged push has no capability and is denied with
AINATIVE_DIRECT_PUSH_DENIED. This module is transport-agnostic; the
authenticated local IPC (ADR-0015 section 2) carries these calls in MV-19.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import secrets
import time
from typing import Callable

from .git_authority import ApprovedGitRemote, GitTransportPolicy
from .schema import PushIntentDigest, digest as canonical_digest


DIRECT_PUSH_DENIED = "AINATIVE_DIRECT_PUSH_DENIED"
CAPABILITY_EXPIRED = "AINATIVE_PUSH_CAPABILITY_EXPIRED"
CAPABILITY_REPLAYED = "AINATIVE_PUSH_CAPABILITY_REPLAYED"
CAPABILITY_MISMATCH = "AINATIVE_PUSH_CAPABILITY_MISMATCH"
REFS_MISMATCH = "AINATIVE_PUSH_REFS_MISMATCH"
DOMAIN_MISMATCH = "AINATIVE_PUSH_DOMAIN_MISMATCH"
CHECKOUT_MISMATCH = "AINATIVE_PUSH_CHECKOUT_MISMATCH"


def _remote_digest(remote: ApprovedGitRemote) -> str:
    return canonical_digest({
        "fetch": remote.canonical_fetch_url,
        "push": remote.canonical_push_url,
        "provider": remote.provider_type,
        "stable_id": remote.stable_repository_id,
        "owner": remote.required_owner_org,
        "visibility": remote.required_visibility_for_push.value,
        "refs": sorted(remote.allowed_refs),
        "require_stable": remote.require_stable_repository_id,
    })


def _policy_digest(policy: GitTransportPolicy) -> str:
    return canonical_digest({
        "protocols": sorted(policy.protocol_allowlist),
        "executable": policy.transport_executable_identity,
        "proxy": policy.proxy,
        "ssh_command": policy.ssh_command,
        "credential_helper": policy.credential_helper,
        "ssh_peer": policy.ssh_peer_policy,
        "tls_peer": policy.tls_peer_policy,
        "digest": policy.effective_transport_config_digest,
    })


@dataclass(frozen=True)
class PushIntent:
    source_oid: str
    expected_remote_base_oid: str
    target_ref: str
    exact_refspec: str
    approved_remote: ApprovedGitRemote
    transport_policy: GitTransportPolicy
    candidate_object_set_digest: str
    scan_result_digest: str
    expected_git_identity: str

    def digest(self) -> str:
        return PushIntentDigest(
            source_oid=self.source_oid,
            expected_remote_base_oid=self.expected_remote_base_oid,
            target_ref=self.target_ref,
            exact_refspec=self.exact_refspec,
            approved_git_remote_digest=_remote_digest(self.approved_remote),
            git_transport_policy_digest=_policy_digest(self.transport_policy),
            candidate_object_set_digest=self.candidate_object_set_digest,
            scan_result_digest=self.scan_result_digest,
            expected_git_identity=self.expected_git_identity,
        ).digest()

    def refspec_source(self) -> str:
        return self.exact_refspec.split(":", 1)[0].lstrip("+")


@dataclass(frozen=True)
class GovernedPushCapability:
    """Single-use capability; normal representations never reveal the nonce."""

    security_domain_id: str
    checkout_identity: str
    push_intent_digest: str
    source_oid: str
    exact_refspec: str
    expires_at: float
    _nonce: str = field(repr=False, compare=False)

    def __str__(self) -> str:
        return "<redacted>"

    def __repr__(self) -> str:
        return "GovernedPushCapability(<redacted>)"


@dataclass(frozen=True)
class PushRefLine:
    local_ref: str
    local_oid: str
    remote_ref: str
    remote_oid: str


@dataclass(frozen=True)
class PushAuthorization:
    decision: str
    code: str
    reason: str


def parse_pre_push_lines(stdin_text: str) -> tuple[PushRefLine, ...]:
    lines = []
    for raw in stdin_text.splitlines():
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 4:
            raise ValueError("pre-push lines must contain exactly four fields")
        lines.append(PushRefLine(*parts))
    return tuple(lines)


class GovernedPushAuthority:
    """Runtime-side owner of push capabilities for one domain and checkout."""

    def __init__(
        self,
        security_domain_id: str,
        checkout_identity: str,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl_seconds: int = 300,
    ):
        if not security_domain_id or not checkout_identity:
            raise ValueError("push authority requires domain and checkout identities")
        if ttl_seconds <= 0:
            raise ValueError("push capability requires a positive lifetime")
        self._security_domain_id = security_domain_id
        self._checkout_identity = checkout_identity
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._issued: dict[str, tuple["PushIntent", float]] = {}

    def issue(self, intent: PushIntent) -> GovernedPushCapability:
        if not intent.source_oid or not intent.target_ref or not intent.exact_refspec:
            raise ValueError("push intent requires source, target ref and exact refspec")
        if ":" not in intent.exact_refspec:
            raise ValueError("push intent requires an exact src:dst refspec")
        nonce = secrets.token_urlsafe(32)
        expires_at = self._clock() + self._ttl_seconds
        self._issued[nonce] = (intent, expires_at)
        return GovernedPushCapability(
            security_domain_id=self._security_domain_id,
            checkout_identity=self._checkout_identity,
            push_intent_digest=intent.digest(),
            source_oid=intent.source_oid,
            exact_refspec=intent.exact_refspec,
            expires_at=expires_at,
            _nonce=nonce,
        )

    def authorize(self, capability: GovernedPushCapability | None, stdin_text: str) -> PushAuthorization:
        if not isinstance(capability, GovernedPushCapability) or not isinstance(capability._nonce, str):
            return PushAuthorization("DENY", DIRECT_PUSH_DENIED, "no governed push capability is present")
        if capability.security_domain_id != self._security_domain_id:
            return PushAuthorization("DENY", DOMAIN_MISMATCH, "push capability belongs to another security domain")
        if capability.checkout_identity != self._checkout_identity:
            return PushAuthorization("DENY", CHECKOUT_MISMATCH, "push capability belongs to another checkout")
        record = self._issued.get(capability._nonce)
        if record is None:
            return PushAuthorization("DENY", CAPABILITY_REPLAYED, "push capability was already consumed or never issued")
        intent, expires_at = record
        if self._clock() > expires_at:
            self._issued.pop(capability._nonce, None)
            return PushAuthorization("DENY", CAPABILITY_EXPIRED, "push capability has expired")
        if (
            capability.push_intent_digest != intent.digest()
            or capability.source_oid != intent.source_oid
            or capability.exact_refspec != intent.exact_refspec
        ):
            return PushAuthorization("DENY", CAPABILITY_MISMATCH, "push capability does not match its issued intent")
        try:
            lines = parse_pre_push_lines(stdin_text)
        except ValueError:
            return PushAuthorization("DENY", REFS_MISMATCH, "pre-push input is malformed")
        if len(lines) != 1:
            return PushAuthorization("DENY", REFS_MISMATCH, "a governed push authorizes exactly one ref transaction")
        line = lines[0]
        if self._normalize_oid(line.local_oid) != self._normalize_oid(intent.source_oid):
            return PushAuthorization("DENY", REFS_MISMATCH, "stdin local object does not match the push intent source")
        if line.remote_ref != intent.target_ref:
            return PushAuthorization("DENY", REFS_MISMATCH, "stdin remote ref does not match the push intent target")
        if self._normalize_oid(line.remote_oid) != self._normalize_oid(intent.expected_remote_base_oid):
            return PushAuthorization("DENY", REFS_MISMATCH, "stdin remote base does not match the push intent")
        source_ref = intent.refspec_source()
        if source_ref.startswith("refs/") and line.local_ref != source_ref:
            return PushAuthorization("DENY", REFS_MISMATCH, "stdin local ref does not match the push intent refspec")
        self._issued.pop(capability._nonce, None)
        return PushAuthorization("ALLOW", "OK", "governed push authorized and capability consumed")

    @staticmethod
    def _normalize_oid(value: str) -> str:
        return value.strip().lower()