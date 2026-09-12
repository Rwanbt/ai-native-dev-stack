"""Consolidation: collect, cluster, propose. Advisory only (row 3).

The cycle composes the resolution owner (normative conflict-before-dedup
order and confirmed-identity discipline), the support summary and the
staleness evaluator. It proposes one outcome per candidate and applies
NONE of them: no transition, no write, no promotion, no authority
escalation. SUPERSEDE is part of the vocabulary but is never proposed
automatically - it requires explicit human intent by construction.
NEEDS_EVIDENCE fires on the ABSENCE of any support, never on a hardcoded
sufficiency threshold (thresholds stay measurement-gated).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import resolution as resolutionlib
from . import staleness as stalenesslib
from . import store as storelib

ADD = "ADD"
MERGE = "MERGE"
SUPERSEDE = "SUPERSEDE"
REJECT = "REJECT"
NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
NEEDS_HUMAN = "NEEDS_HUMAN"
OUTCOMES = (ADD, MERGE, SUPERSEDE, REJECT, NEEDS_EVIDENCE, NEEDS_HUMAN)
NON_PROPOSABLE = (SUPERSEDE,)

TERMINAL_STATES = frozenset({"REJECTED", "PROMOTED", "SUPERSEDED"})


def _outcome_for(verdict: str, support_total: int) -> str:
    if verdict == resolutionlib.DUPLICATE:
        return MERGE
    if verdict == resolutionlib.TOMBSTONE:
        return REJECT
    if verdict in (resolutionlib.CONFLICT, resolutionlib.ADVISORY):
        return NEEDS_HUMAN
    return ADD if support_total else NEEDS_EVIDENCE


outcome_for = _outcome_for


def _confirmed_identities(records: list[dict]) -> frozenset[str]:
    keys = []
    for record in records:
        provenance = record.get("provenance")
        identity = record.get("identity")
        if (isinstance(provenance, dict) and provenance.get("identity_confirmed_by")
                and isinstance(identity, dict) and identity.get("identity_key")):
            keys.append(identity["identity_key"])
    return frozenset(keys)


def consolidate(project: Path) -> dict[str, Any]:
    """One advisory pass over the store. Reads only; applies nothing."""

    records = storelib.list_candidates(Path(project))
    reviewable = [record for record in records
                  if record.get("state") not in TERMINAL_STATES]
    skipped = len(records) - len(reviewable)
    confirmed = _confirmed_identities(records)
    proposals = []
    for record in reviewable:
        candidate_id = str(record.get("candidate_id"))
        supports = storelib.list_supports(Path(project), candidate_id)
        verdict = resolutionlib.resolve(
            record, existing=[item for item in records if item is not record],
            confirmed_identities=confirmed, supports=supports)
        outcome = _outcome_for(verdict["verdict"], verdict["support"]["total"])
        proposal: dict[str, Any] = {
            "candidate_id": candidate_id,
            "outcome": outcome,
            "verdict": verdict["verdict"],
            "reason": verdict.get("reason"),
            "support_total": verdict["support"]["total"]}
        dependencies = record.get("dependencies")
        if dependencies:
            result = stalenesslib.evaluate(project, dependencies)
            decay = stalenesslib.decay_class(record)
            proposal["staleness"] = result["signal"]
            proposal["retrieval_penalty"] = stalenesslib.retrieval_penalty(result["signal"], decay)
            proposal["review_priority"] = stalenesslib.review_priority(result["signal"], decay)
        proposals.append(proposal)
    return {"proposals": proposals, "scanned": len(records),
            "skipped_terminal": skipped,
            "note": "advisory only; no transition, no write, no promotion"}
