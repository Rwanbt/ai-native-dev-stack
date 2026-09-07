"""Evidence accumulation: reinforce one candidate, never duplicate it.

Repetition of the same observation appends evidence to the existing
candidate (idempotently — an identical item is acknowledged, not stored
twice). Scores are prioritisation aids, never authority: `sufficiency`
is a deterministic, documented rule the reviewer can read, not a model
judgement. Verification-run items arrive ONLY as caller-supplied
serialized records (ADR-0011 section 3); nothing here executes or judges
verifications.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import store as storelib
from .candidate import TERMINAL, scan_secrets, validate_evidence_item
from .errors import KnowledgeError

STRONG_TYPES = frozenset({"USER_CONFIRMATION", "VERIFICATION_RUN", "TEST", "SOURCE_CODE"})
MIN_WEAK_COUNT = 2


def sufficiency(evidence: list[dict]) -> tuple[bool, str]:
    """Whether accumulated evidence supports promotion review. Pure function."""

    kinds = [item.get("type") for item in evidence]
    strong = sorted({kind for kind in kinds if kind in STRONG_TYPES})
    if strong:
        return True, f"strong evidence present: {', '.join(strong)}"
    if len(evidence) >= MIN_WEAK_COUNT:
        return False, (f"{len(evidence)} weak observations without a strong one "
                       f"(need 1 of {sorted(STRONG_TYPES)})")
    if not evidence:
        return False, "no evidence"
    return False, "single weak observation (need 2 weak, or 1 strong)"


def add_evidence(project: Path, candidate_id: str, item: dict[str, Any], *,
                 actor: str = "unknown") -> tuple[dict, bool]:
    """Append one evidence item. Returns (record, added). Refuses secrets."""

    current = storelib.inspect_candidate(project, candidate_id)
    if current["status"] in TERMINAL:
        raise KnowledgeError("KNOWLEDGE_BAD_TRANSITION",
                             f"candidate {candidate_id} is {current['status']}; "
                             "evidence cannot reinforce a terminal candidate",
                             current=current["status"])
    evidence_item = validate_evidence_item(item)
    hits = scan_secrets(json.dumps(evidence_item, sort_keys=True, default=str))
    if hits:
        raise KnowledgeError("KNOWLEDGE_SECRET_REJECTED",
                             f"evidence carries a secret pattern ({sorted(hits)}); "
                             "nothing was persisted",
                             patterns=sorted(hits))
    key = (evidence_item["type"], evidence_item["locator"], evidence_item["digest"])
    known = {(entry.get("type"), entry.get("locator"), entry.get("digest"))
             for entry in current["evidence"]}
    if key in known:
        return current, False
    updated = dict(current)
    updated["evidence"] = [*current["evidence"], evidence_item]
    stored = storelib.update_record(project, candidate_id, updated,
                                    operation="EVIDENCE",
                                    detail={"type": evidence_item["type"],
                                            "locator": evidence_item["locator"]},
                                    actor=actor)
    return stored, True


__all__ = ["STRONG_TYPES", "MIN_WEAK_COUNT", "sufficiency", "add_evidence"]