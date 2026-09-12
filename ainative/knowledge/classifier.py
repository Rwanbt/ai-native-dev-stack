"""Advisory classification: suggest a kind, never assign one.

Ported from the legacy reference implementation (knowledge-lifecycle@9eb5422)
onto the current K1 candidate model. The classifier proposes; nothing else
happens because it proposed. `suggest` is a pure keyword heuristic with stated
reasons - a semantic model may replace the heuristic later, but the output
contract (kind plus reasons, advisory only) does not change. The suggestion is
never stored on a candidate and never influences a state transition.
"""
from __future__ import annotations


RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("FAILURE_PATTERN", ("flaky", "failure", "bug", "regress", "crash", "broken"),
     "failure vocabulary"),
    ("ARCHITECTURE_DECISION", ("decid", "adr", "architect", "trade-off", "tradeoff"),
     "decision vocabulary"),
    ("USER_PREFERENCE", ("prefer", "like", "dislike", "always ask", "never ask"),
     "preference vocabulary"),
    ("WORKFLOW_RULE", ("workflow", "process", "review", "checklist", "release"),
     "workflow vocabulary"),
    ("RESEARCH_KNOWLEDGE", ("research", "stud", "survey", "compar", "benchmark"),
     "research vocabulary"),
    ("INCIDENT_KNOWLEDGE", ("incident", "outage", "postmortem", "downtime"),
     "incident vocabulary"),
    ("PROJECT_RULE", ("must", "never", "always", "required", "forbidden", "shall"),
     "normative vocabulary"),
)


def suggest(claim: str, *, module: str | None = None) -> dict:
    """One suggested kind plus the reasons. Pure function, advisory only."""

    lowered = claim.lower()
    hits = [(kind, reason) for kind, words, reason in RULES
            if any(word in lowered for word in words)]
    if module is not None and not any(kind == "MODULE_INVARIANT" for kind, _ in hits):
        hits.append(("MODULE_INVARIANT", "a owning module was named"))
    if not hits:
        return {"kind": "UNKNOWN", "reasons": ["no heuristic matched"]}
    return {"kind": hits[0][0], "reasons": [reason for _, reason in hits]}


__all__ = ["RULES", "suggest"]
