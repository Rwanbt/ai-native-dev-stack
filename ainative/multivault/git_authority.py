"""Approved remote identity, effective transport validation and fetch evidence.

ADR-0016 sections 1-7 and 11. Declarations are trusted operator data; provider
observations are inputs produced outside repository authority. Anything the
observer cannot establish is denied for sensitive classifications. This module
performs no network access.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import fnmatch
import json
import re
from typing import Mapping, Sequence
from urllib.parse import urlsplit

from .schema import SecurityClassification, canonical_json


class Visibility(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


@dataclass(frozen=True)
class ApprovedGitRemote:
    canonical_fetch_url: str
    canonical_push_url: str
    provider_type: str
    stable_repository_id: str | None
    required_owner_org: str
    required_visibility_for_push: Visibility
    allowed_refs: tuple[str, ...]
    require_stable_repository_id: bool = True


@dataclass(frozen=True)
class ObservedRepositoryIdentity:
    provider_type: str
    stable_repository_id: str | None
    owner_org: str | None
    visibility: Visibility | None
    effective_fetch_url: str
    effective_push_url: str


@dataclass(frozen=True)
class GitTransportPolicy:
    protocol_allowlist: tuple[str, ...]
    transport_executable_identity: str
    proxy: str | None
    ssh_command: str | None
    credential_helper: str | None
    ssh_peer_policy: str
    tls_peer_policy: str
    effective_transport_config_digest: str


@dataclass(frozen=True)
class ObservedTransport:
    protocol: str
    transport_executable_identity: str | None
    proxy: str | None
    ssh_command: str | None
    credential_helper: str | None
    effective_transport_config_digest: str | None


@dataclass(frozen=True)
class RemoteVerdict:
    decision: str
    reason: str


@dataclass(frozen=True)
class FetchTransferEvidence:
    approved_remote: ApprovedGitRemote
    transport_policy: GitTransportPolicy
    requested_refs: tuple[str, ...]
    effective_transport_config_digest: str
    verified_remote_identity: ObservedRepositoryIdentity
    verified_at: str


@dataclass(frozen=True)
class FetchEvidenceResult:
    decision: str
    reason: str
    evidence: FetchTransferEvidence | None


REPOSITORY_STATE_SCHEMA_VERSION = 1

_SCP_LIKE = re.compile(r"^(?P<user>[^@/:]+)@(?P<host>[^:/]+):(?P<path>.+)$")

_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\\\/]")
_DEFAULT_PORTS = {"https": 443, "http": 80, "ssh": 22}


def normalize_remote_url(url: str) -> str | None:
    """Canonical comparison form; userinfo is excluded from URL identity."""
    value = (url or "").strip()
    if not value:
        return None
    if "://" not in value and (_WINDOWS_ABSOLUTE_PATH.match(value) or value.startswith("/")):
        return normalize_remote_url("file:///" + value.replace("\\", "/").lstrip("/"))
    scp = _SCP_LIKE.match(value)
    if scp and "://" not in value:
        value = f"ssh://{scp.group('user')}@{scp.group('host')}/{scp.group('path')}"
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme == "file":
        path = parsed.path.rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if not path:
            return None
        return f"file://{path}"
    if scheme not in {"https", "http", "ssh", "git"} or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    port_suffix = f":{port}" if port and port != _DEFAULT_PORTS.get(scheme) else ""
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path:
        return None
    return f"{scheme}://{parsed.hostname.lower()}{port_suffix}{path}"


def _has_inline_credentials(url: str) -> bool:
    if "://" not in (url or ""):
        return False
    try:
        return bool(urlsplit(url).password)
    except ValueError:
        return True


def ref_is_allowed(approved: ApprovedGitRemote, ref: str) -> bool:
    return any(fnmatch.fnmatchcase(ref, pattern) for pattern in approved.allowed_refs)


def validate_remote(
    approved: ApprovedGitRemote,
    observed: ObservedRepositoryIdentity,
    classification: SecurityClassification,
) -> RemoteVerdict:
    if observed.provider_type != approved.provider_type:
        return RemoteVerdict("DENY", "observed provider type does not match the approved remote")
    if _has_inline_credentials(observed.effective_fetch_url) or _has_inline_credentials(observed.effective_push_url):
        return RemoteVerdict("DENY", "effective remote URL embeds credentials")
    expected_fetch = normalize_remote_url(approved.canonical_fetch_url)
    expected_push = normalize_remote_url(approved.canonical_push_url)
    actual_fetch = normalize_remote_url(observed.effective_fetch_url)
    actual_push = normalize_remote_url(observed.effective_push_url)
    if not (expected_fetch and expected_push and actual_fetch and actual_push):
        return RemoteVerdict("DENY", "remote URL cannot be normalized")
    if expected_fetch != actual_fetch or expected_push != actual_push:
        return RemoteVerdict("DENY", "effective remote URL does not match the approved remote")
    requires_identity = approved.require_stable_repository_id or classification in (
        SecurityClassification.CONFIDENTIAL,
        SecurityClassification.CRITICAL,
    )
    if requires_identity:
        if not approved.stable_repository_id:
            return RemoteVerdict("DENY", "approved remote does not pin a stable repository identity")
        if observed.stable_repository_id != approved.stable_repository_id:
            return RemoteVerdict("DENY", "stable repository identity does not match the approved remote")
    elif approved.stable_repository_id and observed.stable_repository_id not in (None, approved.stable_repository_id):
        return RemoteVerdict("DENY", "stable repository identity does not match the approved remote")
    if (observed.owner_org or "").casefold() != approved.required_owner_org.casefold():
        return RemoteVerdict("DENY", "repository owner/organization does not match the approved remote")
    if observed.visibility is None or observed.visibility is not approved.required_visibility_for_push:
        return RemoteVerdict("DENY", "repository visibility does not match the required push visibility")
    return RemoteVerdict("ALLOW", "remote identity, URL, owner and visibility match the approved remote")


def validate_transport(policy: GitTransportPolicy, observed: ObservedTransport) -> RemoteVerdict:
    if not policy.effective_transport_config_digest:
        return RemoteVerdict("DENY", "transport policy has no effective configuration digest")
    if observed.protocol not in policy.protocol_allowlist:
        return RemoteVerdict("DENY", "transport protocol is not in the allowlist")
    if not observed.transport_executable_identity or observed.transport_executable_identity != policy.transport_executable_identity:
        return RemoteVerdict("DENY", "transport executable identity does not match the policy")
    if observed.proxy != policy.proxy:
        return RemoteVerdict("DENY", "proxy configuration does not match the transport policy")
    if observed.ssh_command != policy.ssh_command:
        return RemoteVerdict("DENY", "SSH command configuration does not match the transport policy")
    if observed.credential_helper != policy.credential_helper:
        return RemoteVerdict("DENY", "credential helper does not match the transport policy")
    if observed.effective_transport_config_digest != policy.effective_transport_config_digest:
        return RemoteVerdict("DENY", "effective transport configuration digest does not match the policy")
    return RemoteVerdict("ALLOW", "effective transport matches the policy")


def build_fetch_evidence(
    approved_remote: ApprovedGitRemote,
    transport_policy: GitTransportPolicy,
    observed_remote: ObservedRepositoryIdentity,
    observed_transport: ObservedTransport,
    requested_refs: tuple[str, ...],
    verified_at: str,
    classification: SecurityClassification,
) -> FetchEvidenceResult:
    remote_verdict = validate_remote(approved_remote, observed_remote, classification)
    if remote_verdict.decision != "ALLOW":
        return FetchEvidenceResult("DENY", remote_verdict.reason, None)
    transport_verdict = validate_transport(transport_policy, observed_transport)
    if transport_verdict.decision != "ALLOW":
        return FetchEvidenceResult("DENY", transport_verdict.reason, None)
    if not requested_refs or not verified_at:
        return FetchEvidenceResult("DENY", "fetch evidence requires requested refs and a verification timestamp", None)
    for ref in requested_refs:
        if not ref_is_allowed(approved_remote, ref):
            return FetchEvidenceResult("DENY", f"requested ref {ref} is not allowed by the approved remote", None)
    evidence = FetchTransferEvidence(
        approved_remote=approved_remote,
        transport_policy=transport_policy,
        requested_refs=tuple(requested_refs),
        effective_transport_config_digest=observed_transport.effective_transport_config_digest or "",
        verified_remote_identity=observed_remote,
        verified_at=verified_at,
    )
    return FetchEvidenceResult("ALLOW", "fetch transfer evidence is complete", evidence)


@dataclass(frozen=True)
class LastVerifiedRepositoryState:
    approved_remotes: tuple[str, ...]
    refs: tuple[tuple[str, str], ...]
    index_tree_digest: str
    worktree_security_digest: str
    last_fetch_evidence_digest: str
    verified_at: str
    hooks_path_digest: str = ""
    schema_version: int = REPOSITORY_STATE_SCHEMA_VERSION

    def encode(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "approved_remotes": sorted(self.approved_remotes),
            "refs": [list(pair) for pair in sorted(self.refs)],
            "index_tree_digest": self.index_tree_digest,
            "worktree_security_digest": self.worktree_security_digest,
            "last_fetch_evidence_digest": self.last_fetch_evidence_digest,
            "verified_at": self.verified_at,
            "hooks_path_digest": self.hooks_path_digest,
        }
        return canonical_json(payload).decode("utf-8") + "\n"

    @staticmethod
    def decode(payload: str) -> "LastVerifiedRepositoryState":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("repository state is not valid JSON") from error
        if not isinstance(data, dict) or data.get("schema_version") != REPOSITORY_STATE_SCHEMA_VERSION:
            raise ValueError("repository state schema is unsupported")
        refs = data.get("refs")
        if not isinstance(refs, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in refs):
            raise ValueError("repository state refs are malformed")
        remotes = data.get("approved_remotes")
        if not isinstance(remotes, list) or any(not isinstance(url, str) for url in remotes):
            raise ValueError("repository state remotes are malformed")
        try:
            return LastVerifiedRepositoryState(
                approved_remotes=tuple(remotes),
                refs=tuple((str(pair[0]), str(pair[1])) for pair in refs),
                index_tree_digest=str(data["index_tree_digest"]),
                worktree_security_digest=str(data["worktree_security_digest"]),
                last_fetch_evidence_digest=str(data["last_fetch_evidence_digest"]),
                verified_at=str(data["verified_at"]),
                hooks_path_digest=str(data.get("hooks_path_digest", "")),
            )
        except (KeyError, TypeError) as error:
            raise ValueError("repository state fields are malformed") from error


def compare_repository_state(
    recorded: LastVerifiedRepositoryState,
    current: LastVerifiedRepositoryState,
) -> tuple[str, ...]:
    differences = []
    if sorted(recorded.approved_remotes) != sorted(current.approved_remotes):
        differences.append("remotes-changed")
    if sorted(recorded.refs) != sorted(current.refs):
        differences.append("refs-changed")
    if recorded.index_tree_digest != current.index_tree_digest:
        differences.append("index-tree-changed")
    if recorded.worktree_security_digest != current.worktree_security_digest:
        differences.append("worktree-changed")
    if recorded.hooks_path_digest != current.hooks_path_digest:
        differences.append("hooks-path-changed")
    return tuple(differences)


def unapproved_remotes(
    declared: Mapping[str, Sequence[str]],
    approved: Sequence[ApprovedGitRemote],
) -> tuple[str, ...]:
    approved_urls = set()
    for remote in approved:
        for url in (remote.canonical_fetch_url, remote.canonical_push_url):
            normalized = normalize_remote_url(url)
            if normalized:
                approved_urls.add(normalized)
    unapproved = []
    for name, urls in declared.items():
        normalized = {normalize_remote_url(url) for url in urls}
        normalized.discard(None)
        if not normalized or not normalized <= approved_urls:
            unapproved.append(name)
    return tuple(sorted(unapproved))