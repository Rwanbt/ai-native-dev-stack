"""Root-specific identity_key grammar (B1 S6-S8). No free-form fallback.

Validation is a pure pipeline: proposal, root parse, shape check, scope
resolution, registry check, vocabulary check, bounds, audit-safety
screen. Developer confirmation and persistence are explicit caller
steps (PR3/CLI), never implied. Registries are injected — this module
owns the grammar, the project owns its names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errors import KnowledgeError

MODULE = "module"
PROJECT = "project"
REPO = "repo"
GLOBAL = "global"
ROOTS = frozenset({MODULE, PROJECT, REPO, GLOBAL})

REPO_AREAS = frozenset({"build", "ci", "docs", "release", "security",
                        "testing", "tooling", "workflow", "dependencies"})

ENGINE_VOCABULARY_VERSION = 1
ENGINE_VOCABULARY = frozenset({
    "retry", "timeout", "budget", "cache", "ttl", "limit", "policy",
    "rule", "format", "path", "scope", "target", "source", "index",
    "context", "session", "audit", "schema", "state", "graph",
    "review", "test", "testing", "build", "ci", "docs", "release",
    "workflow", "convention", "invariant", "pattern", "failure",
    "recovery", "lock", "digest", "claim", "support", "tombstone",
    "attempts", "delay", "backoff", "size", "count", "window",
    "retention", "expiry", "access", "visibility", "owner",
})

_SEGMENT = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")
MAX_SEGMENTS = 6
MAX_KEY_CHARS = 253

# Quarantine v0 screen (B1 S7/S8/S11): secret-bearing identifiers are
# refused before anything else. The fail-closed quarantine with an
# unavailable-scanner refusal is PR4; this builtin is always available
# and is superseded, not bypassed, by it.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|client[_-]?secret|secret[_-]?key|auth[_-]?token|"
               r"access[_-]?token|password|passwd|bearer)\s*[:=]"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
)


def _secret_hit(text: str) -> str | None:
    lowered = text.lower()
    for pattern in _SECRET_PATTERNS:
        if pattern.search(lowered):
            return pattern.pattern[:40]
    return None


@dataclass(frozen=True)
class Identity:
    """A validated key. Construction only via `parse_identity`."""

    key: str
    root: str
    segments: tuple[str, ...]
    scope: str

    def to_record(self) -> dict[str, Any]:
        return {"identity_key": self.key, "root": self.root,
                "segments": list(self.segments), "scope": self.scope,
                "identity_key_grammar_version": 1}


def parse_identity(key: Any, *, modules: frozenset[str] | set[str],
                   project_slug: str,
                   repo_areas: frozenset[str] | set[str] = REPO_AREAS,
                   shared_roots: frozenset[str] | set[str] = frozenset(),
                   vocabulary: frozenset[str] | set[str] = ENGINE_VOCABULARY
                   ) -> Identity:
    """Validate a proposed key through the B1 S8 pipeline. Pure function."""

    if not isinstance(key, str) or not key:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             "identity key must be a nonempty string")
    if len(key) > MAX_KEY_CHARS:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             f"identity key exceeds {MAX_KEY_CHARS} chars")
    parts = key.split("/")
    if len(parts) < 3:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             "identity key needs root plus at least two segments")
    if len(parts) > MAX_SEGMENTS + 1:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             f"identity key exceeds {MAX_SEGMENTS} segments")
    root = parts[0]
    if root not in ROOTS:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             f"unknown identity root {root!r}")
    for segment in parts[1:]:
        if not _SEGMENT.match(segment):
            raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                                 f"illegal segment {segment!r} "
                                 "(lowercase kebab, 1-64 chars)")
    head, rest = parts[1], parts[2:]
    if root == MODULE:
        if head not in set(modules):
            raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                                 f"unknown module {head!r}")
        scope = f"module/{head}"
    elif root == PROJECT:
        if head != project_slug:
            raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                                 f"project slug must equal {project_slug!r}")
        scope = f"project/{head}"
    elif root == REPO:
        if head not in set(repo_areas):
            raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                                 f"unknown repo area {head!r}")
        scope = "repo"
    else:
        if head not in set(shared_roots):
            raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                                 f"unknown shared root {head!r}")
        scope = "global"
    vocab = set(vocabulary)
    for segment in rest:
        if segment not in vocab:
            raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                                 f"segment {segment!r} outside the versioned "
                                 f"engineering vocabulary "
                                 f"(v{ENGINE_VOCABULARY_VERSION})")
    hit = _secret_hit(key)
    if hit is not None:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             "identity key fails audit-safety screening")
    return Identity(key=key, root=root, segments=tuple(parts[1:]), scope=scope)


def attest(identity: Identity, *, actor: str) -> dict[str, Any]:
    """Explicit developer confirmation. Separate step, never implied."""

    if not isinstance(actor, str) or not actor:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "confirmation needs an actor")
    from datetime import datetime, timezone
    return {**identity.to_record(), "confirmed_by": actor,
            "confirmed_at": datetime.now(timezone.utc).isoformat()}


__all__ = ["MODULE", "PROJECT", "REPO", "GLOBAL", "ROOTS", "REPO_AREAS",
           "ENGINE_VOCABULARY_VERSION", "ENGINE_VOCABULARY",
           "MAX_SEGMENTS", "MAX_KEY_CHARS", "Identity", "parse_identity",
           "attest"]