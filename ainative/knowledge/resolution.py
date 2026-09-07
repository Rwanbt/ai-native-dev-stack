"""Review pipeline: normalize, identity lookup, conflict, dedup (PR11).

Normative order, enforced structurally by `resolve()`: conflict
detection always runs before dedup, so a contradictory candidate can
never be silently folded into its rival. Deterministic conflict fires
only on confirmed identities (same identity_key, different
assertion_hash); prose contradiction without confirmed identity is
advisory by construction — this module never reads claim text.
Refinement judgments stay human: the pipeline emits UNIQUE, DUPLICATE,
TOMBSTONE, CONFLICT or ADVISORY, never an invented refinement.
Support counting (`support_summary`) feeds review queues; sufficiency
thresholds are measurement-gated (STOP/NARROW/FULL), not hardcoded.
"""

from __future__ import annotations

from typing import Any

from .assertions import normalize_value
from .errors import KnowledgeError

UNIQUE = "UNIQUE"
DUPLICATE = "DUPLICATE"
TOMBSTONE = "TOMBSTONE"
CONFLICT = "CONFLICT"
ADVISORY = "ADVISORY"


def normalize_record(record: dict) -> dict[str, Any]:
    """Extract the comparable core. Pure function, prose-blind."""

    if not isinstance(record, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "candidate not an object")
    identity = record.get("identity", {})
    return {"candidate_id": record.get("candidate_id"),
            "identity_key": identity.get("identity_key")
            if isinstance(identity, dict) else None,
            "assertion_hash": record.get("assertion_hash"),
            "assertion_value": normalize_value(record["assertion_value"])
            if "assertion_value" in record else None}


def lookup_identity(normalized: dict,
                    existing: list[dict]) -> list[dict]:
    """Stored candidates sharing the identity key. Pure function."""

    key = normalized.get("identity_key")
    if not key:
        return []
    return [item for item in existing
            if isinstance(item, dict)
            and isinstance(item.get("identity"), dict)
            and item.get("identity", {}).get("identity_key") == key
            and item.get("candidate_id") != normalized.get("candidate_id")]


def detect_conflict(normalized: dict, holders: list[dict],
                    *, confirmed_identities: frozenset[str] | set[str]
                    ) -> dict[str, Any] | None:
    """Deterministic conflict, confirmed identities only. Pure function."""

    key = normalized.get("identity_key")
    if not key or key not in set(confirmed_identities):
        return None
    rivals = [item for item in holders
              if item.get("assertion_hash") != normalized.get("assertion_hash")]
    if not rivals:
        return None
    return {"verdict": CONFLICT, "identity_key": key,
            "holders": [item.get("candidate_id") for item in rivals],
            "reason": "confirmed identity with differing assertion hash"}


def detect_duplicate(normalized: dict, holders: list[dict],
                     tombstones: frozenset[str] | set[str]
                     ) -> dict[str, Any] | None:
    """Exact-hash match against living holders, then tombstones. Pure."""

    digest = normalized.get("assertion_hash")
    if digest:
        for item in holders:
            if item.get("assertion_hash") == digest:
                return {"verdict": DUPLICATE,
                        "holder": item.get("candidate_id"),
                        "reason": "identical assertion hash"}
        if digest in set(tombstones):
            return {"verdict": TOMBSTONE,
                    "reason": "prior rejection recognized"}
    return None


def support_summary(candidate_id: str, supports: list[dict]) -> dict[str, Any]:
    """Count backing records per kind. No sufficiency verdict (measured later)."""

    kinds: dict[str, int] = {}
    for item in supports:
        if isinstance(item, dict) and item.get("candidate_id") == candidate_id:
            kind = str(item.get("kind", "unknown"))
            kinds[kind] = kinds.get(kind, 0) + 1
    return {"candidate_id": candidate_id, "total": sum(kinds.values()),
            "by_kind": kinds}


def resolve(record: dict, *, existing: list[dict],
            confirmed_identities: frozenset[str] | set[str] = frozenset(),
            tombstones: frozenset[str] | set[str] = frozenset(),
            supports: list[dict] | None = None) -> dict[str, Any]:
    """Full pipeline in normative order. Pure function, no I/O."""

    normalized = normalize_record(record)
    holders = lookup_identity(normalized, existing)
    conflict = detect_conflict(normalized, holders,
                               confirmed_identities=confirmed_identities)
    if conflict is not None:
        return {**conflict, "candidate_id": normalized.get("candidate_id"),
                "support": support_summary(str(normalized.get("candidate_id")),
                                           supports or [])}
    duplicate = detect_duplicate(normalized, holders, tombstones)
    if duplicate is not None:
        return {**duplicate, "candidate_id": normalized.get("candidate_id"),
                "identity_key": normalized.get("identity_key"),
                "support": support_summary(str(normalized.get("candidate_id")),
                                           supports or [])}
    if holders:
        return {"verdict": ADVISORY,
                "candidate_id": normalized.get("candidate_id"),
                "identity_key": normalized.get("identity_key"),
                "reason": "same identity, differing unconfirmed assertions; "
                          "human review required",
                "support": support_summary(str(normalized.get("candidate_id")),
                                           supports or [])}
    return {"verdict": UNIQUE,
            "candidate_id": normalized.get("candidate_id"),
            "identity_key": normalized.get("identity_key"),
            "support": support_summary(str(normalized.get("candidate_id")),
                                       supports or [])}


__all__ = ["UNIQUE", "DUPLICATE", "TOMBSTONE", "CONFLICT", "ADVISORY",
           "normalize_record", "lookup_identity", "detect_conflict",
           "detect_duplicate", "support_summary", "resolve"]
