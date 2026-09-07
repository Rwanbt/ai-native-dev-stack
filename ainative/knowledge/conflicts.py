"""Conflict detection over deterministic signals only.

Implemented in K3: DUPLICATE_CONFLICT (exact or canonical-verbatim
match), SEMANTIC_AMBIGUITY (high lexical overlap on one target — a
human must separate refinement from contradiction), SCOPE_CONFLICT
(same normalized claim, different module scopes). Reserved for later
phases, and NEVER auto-resolved here: VALUE_CONFLICT (needs value
parsing, K4 promotion review), TEMPORAL_CONFLICT (needs the K6
staleness engine), AUTHORITY_CONFLICT (needs cross-target precedence
rules, K4). On conflict the finding is reported; nothing is promoted.
"""

from __future__ import annotations

from pathlib import Path

from . import dedupe as dedupelib
from . import store as storelib

VALUE_CONFLICT = "VALUE_CONFLICT"
SCOPE_CONFLICT = "SCOPE_CONFLICT"
TEMPORAL_CONFLICT = "TEMPORAL_CONFLICT"
AUTHORITY_CONFLICT = "AUTHORITY_CONFLICT"
DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"
SEMANTIC_AMBIGUITY = "SEMANTIC_AMBIGUITY"

IMPLEMENTED = frozenset({DUPLICATE_CONFLICT, SEMANTIC_AMBIGUITY, SCOPE_CONFLICT})


def detect(project: Path, candidate: dict) -> list[dict]:
    """Every deterministic conflict finding. Read-only, never resolves."""

    findings = []
    records = storelib.read_all(project)
    for relation in dedupelib.find_candidate_relations(candidate, records):
        if relation["relation"] == dedupelib.DUPLICATE:
            findings.append({"class": DUPLICATE_CONFLICT,
                             "with": relation["candidate_id"],
                             "explanation": relation["explanation"]})
        elif relation["relation"] == dedupelib.CONFLICTS:
            findings.append({"class": SEMANTIC_AMBIGUITY,
                             "with": relation["candidate_id"],
                             "explanation": relation["explanation"]})
    mine = dedupelib.normalize(candidate["claim"])
    for other in records:
        if (other["candidate_id"] != candidate["candidate_id"]
                and dedupelib.normalize(other["claim"]) == mine
                and (other["scope"].get("module") != candidate["scope"].get("module"))):
            findings.append({"class": SCOPE_CONFLICT,
                             "with": other["candidate_id"],
                             "explanation": "identical claim under a different module scope; "
                                            "promotion must set the scope explicitly"})
    for hit in dedupelib.scan_canonical(project, candidate):
        findings.append({"class": DUPLICATE_CONFLICT,
                         "with": hit["path"],
                         "explanation": hit["explanation"]})
    return findings


__all__ = ["VALUE_CONFLICT", "SCOPE_CONFLICT", "TEMPORAL_CONFLICT",
           "AUTHORITY_CONFLICT", "DUPLICATE_CONFLICT", "SEMANTIC_AMBIGUITY",
           "IMPLEMENTED", "detect"]