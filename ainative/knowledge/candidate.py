"""Knowledge candidates: schema v1, state machine, capture-time validation.

A candidate is a *proposal* for durable knowledge, never truth itself
(INV-04). Classification output is advisory; promotion is a separate,
audited, human-gated step (see `docs/KNOWLEDGE-ARCHITECTURE.md`).
Stdlib only, per ADR-0009.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .errors import KnowledgeError
from .provenance import REQUIRED_KEYS, build_provenance

SCHEMA_VERSION = 1

KINDS = frozenset({
    "USER_PREFERENCE", "PROJECT_RULE", "MODULE_INVARIANT",
    "ARCHITECTURE_DECISION", "FAILURE_PATTERN", "RESEARCH_KNOWLEDGE",
    "INCIDENT_KNOWLEDGE", "WORKFLOW_RULE", "SESSION_ONLY",
    "WORKING_STATE", "DERIVED_FACT", "UNKNOWN",
})

TARGET_HINTS = {
    "USER_PREFERENCE": "user/private memory",
    "PROJECT_RULE": "AGENTS.md",
    "MODULE_INVARIANT": "AI_CONTEXT.md",
    "ARCHITECTURE_DECISION": "docs/adr/",
    "FAILURE_PATTERN": "KNOWN_FAILURE_PATTERNS.md",
    "RESEARCH_KNOWLEDGE": "Vault research/",
    "INCIDENT_KNOWLEDGE": "Vault incidents/",
    "WORKFLOW_RULE": "AGENTS.md/playbook",
    "SESSION_ONLY": "session history",
    "WORKING_STATE": "transient plane",
    "DERIVED_FACT": "regenerate",
    "UNKNOWN": "triage",
}

STATUSES = frozenset({
    "PENDING", "CLASSIFIED", "NEEDS_EVIDENCE", "SUPPORTED", "CONFLICTING",
    "DUPLICATE", "READY_FOR_PROMOTION", "PROMOTED", "REJECTED",
    "SUPERSEDED", "EXPIRED",
})

TRANSITIONS = {
    "PENDING": {"CLASSIFIED", "REJECTED", "EXPIRED"},
    "CLASSIFIED": {"NEEDS_EVIDENCE", "DUPLICATE", "CONFLICTING",
                   "READY_FOR_PROMOTION", "REJECTED"},
    "NEEDS_EVIDENCE": {"SUPPORTED", "DUPLICATE", "CONFLICTING", "EXPIRED", "REJECTED"},
    "SUPPORTED": {"READY_FOR_PROMOTION", "CONFLICTING", "DUPLICATE",
                  "SUPERSEDED", "REJECTED"},
    "CONFLICTING": {"SUPPORTED", "DUPLICATE", "REJECTED", "SUPERSEDED"},
    "DUPLICATE": {"SUPERSEDED", "REJECTED"},
    "READY_FOR_PROMOTION": {"PROMOTED", "REJECTED", "SUPERSEDED", "EXPIRED"},
    "PROMOTED": set(),
    "REJECTED": set(),
    "SUPERSEDED": set(),
    "EXPIRED": set(),
}

TERMINAL = frozenset({"PROMOTED", "REJECTED", "SUPERSEDED", "EXPIRED"})

EVIDENCE_TYPES = frozenset({
    "SOURCE_CODE", "TEST", "ADR", "AI_CONTEXT", "AGENTS_RULE", "KFP",
    "GIT_HISTORY", "VERIFICATION_RUN", "USER_CONFIRMATION",
    "REPEATED_OBSERVATION", "GRAPH_RELATION", "EXTERNAL_DOCUMENTATION",
})

CANDIDATE_ID = re.compile(r"^kc_[0-9a-f]{26}$")
MAX_CLAIM_CHARS = 2000

# Secret detection runs BEFORE persistence; on match the candidate is
# refused with KNOWLEDGE_SECRET_REJECTED and nothing is stored.
# Pattern-based defense in depth: it can miss, so evidence keeps digests
# plus bounded previews, never full logs (see KNOWLEDGE-SECURITY.md).
SECRET_PATTERNS = (
    ("api_key", re.compile(r"(?i)(api[_-]?key|client[_-]?secret|secret[_-]?key)\s*[:=]\s*\S+")),
    ("token", re.compile(r"(?i)(auth[_-]?token|access[_-]?token|bearer)\s*[:=]\s*\S+")),
    ("authorization_header", re.compile(r"(?i)(authorization\s*:\s*bearer|cookie\s*:)")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")),
    ("password", re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+")),
)

_LOCATOR_RESERVED = {"", ".", ".."}


def new_candidate_id() -> str:
    return f"kc_{uuid.uuid4().hex[:26]}"


def validate_locator(locator: str) -> str:
    """Refuse absolute paths, drive anchors, `..` and NUL before storage."""

    if not isinstance(locator, str) or not locator.strip() or "\x00" in locator:
        raise KnowledgeError("KNOWLEDGE_BAD_LOCATOR",
                             f"refusing locator {locator!r}: empty or NUL")
    normalized = locator.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise KnowledgeError("KNOWLEDGE_BAD_LOCATOR",
                             f"refusing locator {locator!r}: absolute path")
    for part in normalized.split("/"):
        if part in _LOCATOR_RESERVED or part.strip() != part:
            raise KnowledgeError("KNOWLEDGE_BAD_LOCATOR",
                                 f"refusing locator {locator!r}: "
                                 f"illegal component {part!r}")
    return normalized


def scan_secrets(*texts: str) -> list[str]:
    """Names of secret patterns found. Pure function, no I/O."""

    hits: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        for text in texts:
            if isinstance(text, str) and pattern.search(text):
                hits.append(name)
                break
    return hits


def validate_evidence_item(item: Any) -> dict:
    if not isinstance(item, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "evidence item is not an object")
    kind = item.get("type")
    if kind not in EVIDENCE_TYPES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown evidence type {kind!r}")
    locator = item.get("locator", "")
    if not isinstance(locator, str):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "evidence locator is not a string")
    if locator:
        validate_locator(locator)
    # VERIFICATION_RUN evidence arrives ONLY as caller-supplied serialized
    # records (digests, identifiers). Knowledge code never executes or
    # judges verifications (ADR-0011 section 3).
    return {"type": kind, "locator": locator,
            "digest": item.get("digest"), "observed_at": item.get("observed_at"),
            "repository_state": item.get("repository_state"),
            "confidence": item.get("confidence", 0.0)}


def validate_candidate(raw: Any) -> dict:
    """Normalize one candidate record, or refuse it. Pure function."""

    if not isinstance(raw, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "candidate is not an object")
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise KnowledgeError("KNOWLEDGE_SCHEMA_UNKNOWN",
                             f"candidate schema_version {version!r} is not "
                             f"supported (reader understands {SCHEMA_VERSION})")
    identifier = raw.get("candidate_id", "")
    if not isinstance(identifier, str) or not CANDIDATE_ID.match(identifier):
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"illegal candidate_id {identifier!r}")
    kind = raw.get("kind", "")
    if kind not in KINDS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"unknown kind {kind!r}")
    claim = raw.get("claim", "")
    if not isinstance(claim, str) or not claim.strip():
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "claim is empty")
    if len(claim) > MAX_CLAIM_CHARS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"claim exceeds {MAX_CLAIM_CHARS} chars")
    status = raw.get("status", "")
    if status not in STATUSES:
        raise KnowledgeError("KNOWLEDGE_BAD_STATUS", f"unknown status {status!r}")
    scope = raw.get("scope")
    if not isinstance(scope, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "scope is not an object")
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "provenance is not an object")
    missing = [key for key in REQUIRED_KEYS if key not in provenance]
    if missing:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"provenance missing {sorted(missing)}")
    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "evidence is not a list")
    normalized_evidence = [validate_evidence_item(item) for item in evidence]
    secret_hits = scan_secrets(
        claim,
        json.dumps(provenance, sort_keys=True, default=str),
        json.dumps(raw.get("source", {}), sort_keys=True, default=str),
        *[str(item.get("locator", "")) for item in normalized_evidence])
    if secret_hits:
        raise KnowledgeError("KNOWLEDGE_SECRET_REJECTED",
                             f"candidate carries a secret pattern ({sorted(secret_hits)}); "
                             "nothing was persisted",
                             patterns=sorted(secret_hits))
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": identifier,
        "project": raw.get("project", ""),
        "scope": {"repository": bool(scope.get("repository", True)),
                  "module": scope.get("module"),
                  "agent": scope.get("agent"),
                  "visibility": scope.get("visibility", "project")},
        "kind": kind,
        "claim": claim,
        "source": raw.get("source", {}),
        "provenance": provenance,
        "evidence": normalized_evidence,
        "confidence": raw.get("confidence", 0.0),
        "status": status,
        "target_hint": raw.get("target_hint") or TARGET_HINTS[kind],
    }


def capture(*, project: str, agent: str, session: str, origin_type: str,
            kind: str, claim: str, module: str | None = None,
            source_paths: tuple = (), repository=None) -> dict:
    """Build a PENDING candidate. Refuses malformed input and secrets."""

    if kind not in KINDS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"unknown kind {kind!r}")
    provenance = build_provenance(project=project, agent=agent, session=session,
                                  origin_type=origin_type,
                                  source_paths=source_paths,
                                  repository=repository)
    return validate_candidate({
        "schema_version": SCHEMA_VERSION,
        "candidate_id": new_candidate_id(),
        "project": project,
        "scope": {"repository": True, "module": module, "agent": agent,
                  "visibility": "project"},
        "kind": kind,
        "claim": claim,
        "source": {"type": origin_type, "session_id": session,
                   "agent": agent, "timestamp": provenance["timestamp"]},
        "provenance": provenance,
        "evidence": [],
        "confidence": 0.0,
        "status": "PENDING",
        "target_hint": TARGET_HINTS[kind],
    })


def transition(record: dict, to_status: str) -> dict:
    """Move one validated candidate to a new state. Pure function."""

    current = validate_candidate(record)["status"]
    if to_status not in STATUSES:
        raise KnowledgeError("KNOWLEDGE_BAD_STATUS", f"unknown status {to_status!r}")
    if to_status not in TRANSITIONS[current]:
        raise KnowledgeError("KNOWLEDGE_BAD_TRANSITION",
                             f"illegal transition {current} -> {to_status}",
                             current=current, target=to_status)
    updated = dict(validate_candidate(record))
    updated["status"] = to_status
    return updated


__all__ = ["SCHEMA_VERSION", "KINDS", "TARGET_HINTS", "STATUSES", "TRANSITIONS",
           "TERMINAL", "EVIDENCE_TYPES", "CANDIDATE_ID", "MAX_CLAIM_CHARS",
           "SECRET_PATTERNS", "new_candidate_id", "validate_locator",
           "scan_secrets", "validate_evidence_item", "validate_candidate",
           "capture", "transition"]