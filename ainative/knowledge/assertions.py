"""Structured assertions: canonical JSON, domain-separated hash, tombstones.

The authoritative hash path is deterministic only: canonical JSON
(sorted keys, fixed separators) inside the v1 domain
`ainative-knowledge-assertion:v1\\0`. No LLM fuzzy normalization touches
this path. Rejection applies to assertion hashes, so the same exact
assertion is recognized while a changed assertion under one identity
stays reviewable. Tombstones carry hashes only, never raw text.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from .errors import KnowledgeError
from .identity import Identity, screen_secret

NORMALIZATION_VERSION = 1
HASH_ALGORITHM = "sha256"
HASH_DOMAIN = "ainative-knowledge-assertion:v1\x00"

VALUE_TYPES = frozenset({"integer", "string", "boolean", "enum"})


def canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, fixed separators, UTF-8. Pure."""

    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"value is not JSON-canonicalizable: {error}") from error


def normalize_value(value: Any) -> dict[str, Any]:
    """Coerce a structured value to {type, value}. Pure function."""

    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, dict) and set(value) == {"type", "value"} \
            and value.get("type") in VALUE_TYPES:
        return {"type": value["type"], "value": value["value"]}
    raise KnowledgeError("KNOWLEDGE_MALFORMED",
                         f"unsupported assertion value {value!r}")


def assertion_hash(identity: Identity, scope: str, value: Any) -> dict[str, Any]:
    """Hash one structured assertion. Pure function."""

    structured = {"identity_key": identity.key, "scope": scope,
                  "value": normalize_value(value)}
    domain_payload = HASH_DOMAIN + canonical_json(structured)
    digest = sha256(domain_payload.encode("utf-8")).hexdigest()
    return {"identity_key": identity.key, "scope": scope,
            "value": structured["value"], "assertion_hash": digest,
            "assertion_normalization_version": NORMALIZATION_VERSION,
            "hash_algorithm": HASH_ALGORITHM}


def tombstone(assertion_hash_value: str, *, reason: str, actor: str,
              scanner: Any = None) -> dict[str, Any]:
    """Rejection marker over a hash. Hashes only, never raw text."""

    if not isinstance(assertion_hash_value, str) or not assertion_hash_value:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "tombstone needs a hash")
    if not isinstance(reason, str) or not reason:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "tombstone needs a reason")
    if not isinstance(actor, str) or not actor:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "tombstone needs an actor")
    if len(reason) > 500:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "tombstone reason too long")
    from . import quarantine as quarantinelib
    quarantinelib.check(reason, purpose="tombstone reason", scanner=scanner)
    return {"assertion_hash": assertion_hash_value, "reason": reason,
            "actor": actor}


__all__ = ["NORMALIZATION_VERSION", "HASH_ALGORITHM", "HASH_DOMAIN",
           "VALUE_TYPES", "canonical_json", "normalize_value",
           "assertion_hash", "tombstone"]
