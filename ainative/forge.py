"""Resolve the Work Authority from locally observed facts — purely.

Multi-Forge's Work Authority is the remote whose work records are
authoritative for a project: one provider plus a project identity on it.
Deciding *which* remote that is, is the only thing this module does, and it
decides it from facts observed elsewhere — an explicit WorkItem/ChangeRequest
reference, a harness declaration, or the Git remotes someone already read. It
never reaches the network, never looks up a credential, never writes, and never
authorizes a push (ADR-0018).

The rules are ordered and fail closed (ADR-0018 section 2):

1. an explicit WorkItem/ChangeRequest repository reference;
2. an explicit harness-declared authority;
3. exactly one compatible observed candidate;
4. otherwise a refusal — never a guess.

A fork (origin and upstream disagreeing) is `AMBIGUOUS`, never "prefer
origin". A self-hosted host is `unknown`, never inferred from its name:
GitHub.com and GitLab.com are the only hosted forges V1 knows, and inferring
"gitlab" from a hostname is how a generic Git project gets claimed on a forge
it never chose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

from .lifecycle.errors import LifecycleError

PROVIDER_GITHUB = "github"
PROVIDER_GITLAB = "gitlab"
PROVIDER_UNKNOWN = "unknown"

# The only hosts whose provider is a fact rather than a guess.
HOST_HINTS = {"github.com": PROVIDER_GITHUB, "gitlab.com": PROVIDER_GITLAB}


@dataclass(frozen=True)
class WorkAuthorityRef:
    """One provider plus a stable project identity. Not a URL, not a hostname."""

    provider: str
    project: str

    def to_record(self) -> dict:
        return {"provider": self.provider, "project": self.project}

    def __str__(self) -> str:
        return f"{self.provider}:{self.project}"


@dataclass(frozen=True)
class ObservedRemote:
    """A Git remote someone read locally. Evidence, never authority."""

    name: str
    url: str

    @property
    def provider(self) -> str:
        return provider_hint(self.url)

    @property
    def identity(self) -> str | None:
        return project_identity(self.url)

    def to_record(self) -> dict:
        return {"name": self.name, "url": self.url, "provider": self.provider,
                "project": self.identity}


def provider_hint(url: str) -> str:
    """The provider a remote URL *names*: a hosted forge, or `unknown`."""

    host, _ = _host_and_path(url)
    return HOST_HINTS.get(host, PROVIDER_UNKNOWN)


def project_identity(url: str) -> str | None:
    """`owner/name` (or a GitLab subgroup path) for a hosted URL, else None."""

    host, path = _host_and_path(url)
    if host not in HOST_HINTS:
        return None
    cleaned = path.strip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    segments = [segment for segment in cleaned.split("/") if segment]
    if len(segments) < 2:
        return None
    return "/".join(segments)


def _host_and_path(url: str) -> tuple[str, str]:
    """Host and path for both URL shapes Git uses, without guessing a provider."""

    if "://" in url:
        parts = urlsplit(url)
        return (parts.hostname or "").lower(), parts.path
    # scp-like: [user@]host:path
    head, _, path = url.partition(":")
    host = head.rpartition("@")[2]
    return host.lower(), path


def observe_remotes(remotes: Iterable[tuple[str, str]]) -> tuple[ObservedRemote, ...]:
    """(name, url) pairs as observed remotes; a thin adapter for callers."""

    return tuple(ObservedRemote(name=name, url=url) for name, url in remotes)


def resolve_observed_work_authority(*,
                                    explicit: WorkAuthorityRef | None = None,
                                    declared: WorkAuthorityRef | None = None,
                                    remotes: Iterable[ObservedRemote] = (),
                                    ) -> WorkAuthorityRef:
    """The authority the ordered rules accept, or a refusal that says why.

    `explicit` is a WorkItem/ChangeRequest repository reference (priority 1),
    `declared` a harness statement (priority 2), `remotes` locally observed
    evidence (priority 3). Two statements that disagree refuse as
    `WORK_AUTHORITY_MISMATCH`; observation that is not unambiguous refuses as
    `WORK_AUTHORITY_AMBIGUOUS` (a fork) or `WORK_AUTHORITY_UNAVAILABLE`
    (nothing usable was observed).
    """

    if explicit is not None and declared is not None and explicit != declared:
        raise LifecycleError(
            "WORK_AUTHORITY_MISMATCH",
            f"the explicit reference names {explicit} but the harness declares "
            f"{declared}; reconcile them before mutating remote state",
            explicit=explicit.to_record(), declared=declared.to_record())
    if explicit is not None:
        return explicit
    if declared is not None:
        return declared

    candidates: list[WorkAuthorityRef] = []
    for remote in remotes:
        if remote.provider == PROVIDER_UNKNOWN or remote.identity is None:
            continue
        candidate = WorkAuthorityRef(provider=remote.provider, project=remote.identity)
        if candidate not in candidates:
            candidates.append(candidate)

    if len(candidates) == 1:
        return candidates[0]
    observed = [remote.to_record() for remote in remotes]
    if not candidates:
        raise LifecycleError(
            "WORK_AUTHORITY_UNAVAILABLE",
            "no work authority could be resolved locally: no explicit reference, "
            "no harness declaration, and no observed remote names a known forge",
            remotes=observed)
    raise LifecycleError(
        "WORK_AUTHORITY_AMBIGUOUS",
        "several observed remotes name different work authorities: "
        + ", ".join(str(candidate) for candidate in candidates)
        + "; declare the authority explicitly before mutating remote state",
        candidates=[candidate.to_record() for candidate in candidates],
        remotes=observed)


__all__ = ["WorkAuthorityRef", "ObservedRemote", "provider_hint", "project_identity",
           "observe_remotes", "resolve_observed_work_authority",
           "PROVIDER_GITHUB", "PROVIDER_GITLAB", "PROVIDER_UNKNOWN", "HOST_HINTS"]
