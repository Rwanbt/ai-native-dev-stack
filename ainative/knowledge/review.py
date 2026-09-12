"""Review queue: expose the advisory state of candidates. Read-only (row 14).

Composes the resolution owner, the support summary, the staleness evaluator,
the consolidation outcome mapping and the state vocabulary. It exposes
candidates, supports, duplicate and conflict relations, staleness signals and
review priority - plus HONEST status fields: promotion eligibility is
GATE_CLOSED (the K5 gate is not authorized), trust is UNVERIFIED (standard
operator ceremony, never VERIFIED) and representation health is
NOT_APPLICABLE while no promotions exist. No transition, no write, no
promotion, no authority claim.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import consolidation as consolidationlib
from . import resolution as resolutionlib
from . import staleness as stalenesslib
from . import store as storelib

GATE_CLOSED = "GATE_CLOSED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNVERIFIED = "UNVERIFIED"
TRUSTED_OPERATOR_CEREMONY = "TRUSTED_OPERATOR_CEREMONY"
CONFLICT_VERDICTS = (resolutionlib.CONFLICT, resolutionlib.ADVISORY)

_BASE_PRIORITY = {resolutionlib.CONFLICT: 3, resolutionlib.ADVISORY: 3,
                  resolutionlib.TOMBSTONE: 3, resolutionlib.DUPLICATE: 2}


def _base_priority(verdict: str, support_total: int) -> int:
    if verdict == resolutionlib.UNIQUE:
        return 2 if not support_total else 1
    return _BASE_PRIORITY.get(verdict, 1)


def review_queue(project: Path) -> dict[str, Any]:
    """Advisory queue sorted by review priority. Reads only."""

    records = storelib.list_candidates(Path(project))
    reviewable = [record for record in records
                  if record.get("state") not in consolidationlib.TERMINAL_STATES]
    confirmed = consolidationlib._confirmed_identities(records)
    entries = []
    for record in reviewable:
        candidate_id = str(record.get("candidate_id"))
        supports = storelib.list_supports(Path(project), candidate_id)
        verdict = resolutionlib.resolve(
            record, existing=[item for item in records if item is not record],
            confirmed_identities=confirmed, supports=supports)
        outcome = consolidationlib.outcome_for(verdict["verdict"],
                                               verdict["support"]["total"])
        priority = _base_priority(verdict["verdict"], verdict["support"]["total"])
        entry: dict[str, Any] = {
            "candidate_id": candidate_id,
            "state": record.get("state"),
            "kind": record.get("kind"),
            "claim": str(record.get("claim"))[:80],
            "verdict": verdict["verdict"],
            "outcome": outcome,
            "support_total": verdict["support"]["total"],
            "holders": verdict.get("holders", []),
            "review_priority": priority,
        }
        dependencies = record.get("dependencies")
        if dependencies:
            result = stalenesslib.evaluate(project, dependencies)
            decay = stalenesslib.decay_class(record)
            entry["staleness"] = result["signal"]
            entry["retrieval_penalty"] = stalenesslib.retrieval_penalty(
                result["signal"], decay)
            entry["review_priority"] = max(
                priority, stalenesslib.review_priority(result["signal"], decay))
        entries.append(entry)
    entries.sort(key=lambda item: (-item["review_priority"], item["candidate_id"]))
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["outcome"]] = counts.get(entry["outcome"], 0) + 1
    return {"queue": entries, "counts": counts, "scanned": len(records),
            "trust": {"approval_mode": TRUSTED_OPERATOR_CEREMONY,
                      "qualification": UNVERIFIED},
            "promotion": {"eligibility": GATE_CLOSED,
                          "reason": "the K5 gate is not authorized"},
            "representation_health": NOT_APPLICABLE,
            "note": "read-only queue; classification results stay advisory"}


def conflicts(project: Path) -> dict[str, Any]:
    """Only the conflict/advisory entries, with their holders."""

    queue = review_queue(Path(project))
    conflicting = [entry for entry in queue["queue"]
                   if entry["verdict"] in CONFLICT_VERDICTS]
    return {"conflicts": conflicting, "count": len(conflicting),
            "scanned": queue["scanned"]}
