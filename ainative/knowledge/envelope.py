"""Durable-control envelope (B1 S14). Portable metadata only, fail closed."""

from __future__ import annotations

from typing import Any

from .errors import KnowledgeError

SCHEMA_VERSION = 1

RECORD_TYPES = frozenset({"candidate", "support", "tombstone", "audit"})


def wrap(record_type: str, record_id: str, payload: dict) -> dict[str, Any]:
    """One versioned envelope. Pure function."""

    if record_type not in RECORD_TYPES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown record type {record_type!r}")
    if not isinstance(record_id, str) or not record_id:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "record_id must be nonempty")
    if not isinstance(payload, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "payload must be an object")
    return {"schema_version": SCHEMA_VERSION, "record_type": record_type,
            "record_id": record_id, "payload": payload}


def unwrap(raw: Any) -> dict[str, Any]:
    """Read one envelope. Unknown schema fails closed, never reinterpreted."""

    if not isinstance(raw, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "envelope is not an object")
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise KnowledgeError("KNOWLEDGE_SCHEMA_UNKNOWN",
                             f"envelope schema_version {version!r} unsupported "
                             f"(reader understands {SCHEMA_VERSION})")
    if raw.get("record_type") not in RECORD_TYPES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown record type {raw.get('record_type')!r}")
    return {"schema_version": version, "record_type": raw["record_type"],
            "record_id": raw.get("record_id"), "payload": raw.get("payload", {})}


__all__ = ["SCHEMA_VERSION", "RECORD_TYPES", "wrap", "unwrap"]