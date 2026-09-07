"""Consolidation: collect, cluster, verify, recommend. Advisory only.

The cycle replays the K3 checks across the whole store and proposes
one outcome per candidate (ADD, MERGE, SUPERSEDE, REJECT, NEEDS_HUMAN)
without applying any of them: no transition, no write, no promotion.
SUPERSEDE is never proposed (it needs human intent); MERGE means fold
evidence into the surviving holder by hand, then reject the duplicate.
Scheduling is manual (`knowledge consolidate`); no background process
exists by design (plan Phase K7 gate: advisory until proven safe).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import dedupe as dedupelib
from . import review as reviewlib
from . import staleness as stalenesslib
from . import store as storelib
from .candidate import TERMINAL

ADD = "ADD"
MERGE = "MERGE"
SUPERSEDE = "SUPERSEDE"
REJECT = "REJECT"
NEEDS_HUMAN = "NEEDS_HUMAN"

STALE_DRAFT_DAYS = 30


def collect(project: Path) -> dict[str, Any]:
    """Recent candidates, git signals, conflicts. Read-only."""

    records = storelib.read_all(Path(project))
    live = [item for item in records if item["status"] not in TERMINAL]
    changed, git_note = stalenesslib.git_changed(Path(project))
    stale = stalenesslib.impacted(Path(project), changed) if changed else []
    return {"candidates": [item["candidate_id"] for item in live],
            "conflicting": [item["candidate_id"] for item in live
                            if item["status"] == "CONFLICTING"],
            "git_changed": changed, "git_note": git_note,
            "stale_findings": stale, "_records": live}


def cluster(records: list[dict]) -> list[dict[str, Any]]:
    """Union-find over DUPLICATE/REFINEMENT/CONFLICTS pairs. Pure function."""

    parent = list(range(len(records)))

    def _find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def _union(left: int, right: int) -> None:
        parent[_find(left)] = _find(right)

    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            relation, _, _ = dedupelib.classify_pair(
                records[left]["claim"], records[left]["target_hint"],
                records[right]["claim"], records[right]["target_hint"])
            if relation != dedupelib.UNRELATED:
                _union(left, right)
    groups: dict[int, list[dict]] = {}
    for index, record in enumerate(records):
        groups.setdefault(_find(index), []).append(record)
    return [{"members": [item["candidate_id"] for item in members],
             "size": len(members)}
            for members in groups.values() if len(members) > 1]


def _age_days(candidate: dict) -> float | None:
    try:
        stamped = datetime.fromisoformat(
            candidate["provenance"].get("timestamp", ""))
    except (ValueError, TypeError):
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamped).total_seconds() / 86400


def recommend(project: Path, records: list[dict]) -> list[dict[str, Any]]:
    """One advisory outcome per candidate. Read-only, never transitions."""

    proposals = []
    for record in records:
        identifier = record["candidate_id"]
        if record["status"] == "PENDING":
            proposals.append({"candidate_id": identifier,
                              "recommendation": NEEDS_HUMAN,
                              "reason": "classify first (PENDING)"})
            continue
        if record["status"] == "CONFLICTING":
            proposals.append({"candidate_id": identifier,
                              "recommendation": NEEDS_HUMAN,
                              "reason": "unresolved conflict findings"})
            continue
        try:
            preview = reviewlib.preview_verify(Path(project), identifier)
        except Exception as error:
            proposals.append({"candidate_id": identifier,
                              "recommendation": NEEDS_HUMAN,
                              "reason": f"verify undecidable: {error}"})
            continue
        target = preview["to"]
        if target == "DUPLICATE":
            holders = [item["with"] for item in preview["findings"]
                       if item["class"] == "DUPLICATE_CONFLICT"]
            if any(not holder.startswith("kc_") for holder in holders):
                proposals.append({"candidate_id": identifier,
                                  "recommendation": REJECT,
                                  "reason": "already durable in canonical target"})
            else:
                proposals.append({"candidate_id": identifier,
                                  "recommendation": MERGE,
                                  "reason": f"fold evidence into {holders[0] if holders else '?'} "
                                            "by hand, then reject"})
        elif target == "CONFLICTING":
            proposals.append({"candidate_id": identifier,
                              "recommendation": NEEDS_HUMAN,
                              "reason": "ambiguous overlap needs a human"})
        elif target == "SUPPORTED":
            proposals.append({"candidate_id": identifier,
                              "recommendation": ADD,
                              "reason": "supported and unrelated; advance to promotion review"})
        else:
            age = _age_days(record)
            if age is not None and age > STALE_DRAFT_DAYS:
                proposals.append({"candidate_id": identifier,
                                  "recommendation": REJECT,
                                  "reason": f"unevidenced draft older than "
                                            f"{STALE_DRAFT_DAYS} days"})
    return proposals


def consolidate(project: Path) -> dict[str, Any]:
    """Full advisory cycle. The store is identical afterwards."""

    collected = collect(Path(project))
    records = collected.pop("_records")
    clusters = cluster(records)
    return {"collected": {key: (len(value) if isinstance(value, list) else value)
                          for key, value in collected.items()
                          if key != "stale_findings"},
            "stale_findings": collected["stale_findings"],
            "clusters": clusters,
            "recommendations": recommend(Path(project), records)}


__all__ = ["ADD", "MERGE", "SUPERSEDE", "REJECT", "NEEDS_HUMAN",
           "STALE_DRAFT_DAYS", "collect", "cluster", "recommend", "consolidate"]