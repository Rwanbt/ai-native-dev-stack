"""Review pipeline: classify then verify, both human-gated and audited.

`classify` moves PENDING to CLASSIFIED (optionally correcting the kind;
the classifier suggestion stays advisory). `verify` replays the K3
checks — canonical scan, candidate relations, evidence sufficiency —
and moves to NEEDS_EVIDENCE, SUPPORTED, DUPLICATE or CONFLICTING.
Multi-hop moves (CLASSIFIED to SUPPORTED via NEEDS_EVIDENCE) are
applied hop by hop so the audit trail shows every step. CONFLICTING is
a state awaiting a human, never an auto-resolution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import conflicts as conflictslib
from . import evidence as evidencelib
from . import store as storelib
from .candidate import KINDS
from .classifier import suggest
from .errors import KnowledgeError

VERIFY_FROM = frozenset({"CLASSIFIED", "NEEDS_EVIDENCE", "SUPPORTED", "CONFLICTING"})


def classify_candidate(project: Path, candidate_id: str, *,
                       kind: str | None = None,
                       actor: str = "unknown") -> dict:
    """Set the kind (optional) and move PENDING to CLASSIFIED."""

    current = storelib.inspect_candidate(project, candidate_id)
    if current["status"] != "PENDING":
        raise KnowledgeError("KNOWLEDGE_BAD_TRANSITION",
                             f"classify needs PENDING, found {current['status']}",
                             current=current["status"])
    suggestion = suggest(current["claim"], module=current["scope"].get("module"))
    chosen = current["kind"] if kind is None else kind.upper()
    if chosen not in KINDS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"unknown kind {kind!r}")
    updated = dict(current)
    updated["kind"] = chosen
    from .candidate import TARGET_HINTS
    updated["target_hint"] = TARGET_HINTS[chosen]
    storelib.update_record(project, candidate_id, updated,
                           operation="CLASSIFY",
                           detail={"from_kind": current["kind"], "to_kind": chosen,
                                   "suggestion": suggestion},
                           actor=actor)
    return storelib.set_status(project, candidate_id, "CLASSIFIED", actor=actor)


def preview_verify(project: Path, candidate_id: str) -> dict[str, Any]:
    """Decide the verify outcome. Reads only, never writes."""

    current = storelib.inspect_candidate(project, candidate_id)
    if current["status"] not in VERIFY_FROM:
        raise KnowledgeError("KNOWLEDGE_BAD_TRANSITION",
                             f"verify needs one of {sorted(VERIFY_FROM)}, "
                             f"found {current['status']}",
                             current=current["status"])
    findings = conflictslib.detect(project, current)
    duplicates = [item for item in findings
                  if item["class"] == conflictslib.DUPLICATE_CONFLICT]
    ambiguous = [item for item in findings
                 if item["class"] in (conflictslib.SEMANTIC_AMBIGUITY,
                                      conflictslib.SCOPE_CONFLICT)]
    sufficient, reason = evidencelib.sufficiency(current["evidence"])
    if duplicates:
        target = "DUPLICATE"
    elif ambiguous:
        target = "CONFLICTING"
    elif sufficient:
        target = "SUPPORTED"
    else:
        target = "NEEDS_EVIDENCE"
    hops = [] if target == current["status"] else _path(current["status"], target)
    return {"candidate_id": candidate_id,
            "from": current["status"], "to": target,
            "hops": hops,
            "sufficient_evidence": sufficient,
            "sufficiency_reason": reason,
            "findings": findings,
            "report": current}


def verify_candidate(project: Path, candidate_id: str, *,
                     actor: str = "unknown") -> dict[str, Any]:
    """Replay dedupe, conflicts and evidence rules. Returns the report."""

    preview = preview_verify(project, candidate_id)
    applied = []
    for hop in preview["hops"]:
        storelib.set_status(project, candidate_id, hop, actor=actor)
        applied.append(hop)
    final = storelib.inspect_candidate(project, candidate_id)
    return {**preview, "to": final["status"], "hops": applied, "report": final}


def _path(current: str, target: str) -> list[str]:
    """Hop list between review states. Single hop unless documented here.

    WHY only one multi-hop case: findings and evidence grow monotonically
    (records are never edited or deleted), so verify can only move
    forward. A CONFLICTING candidate keeps its findings; NEEDS_EVIDENCE
    from CONFLICTING is therefore unreachable, and any other pair the
    decider emits is a legal single hop — anything else surfaces as
    KNOWLEDGE_BAD_TRANSITION rather than a silent skip.
    """

    if current == "CLASSIFIED" and target == "SUPPORTED":
        return ["NEEDS_EVIDENCE", "SUPPORTED"]
    return [target]


__all__ = ["VERIFY_FROM", "classify_candidate", "preview_verify", "verify_candidate"]