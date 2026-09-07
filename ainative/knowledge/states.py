"""Candidate state machine (B1 S5). Vocabulary frozen; B3/K5 gated.

All fourteen normative states exist as values. Transitions usable
before K5 are implemented; mutation-gated targets
(APPROVED/PROMOTION_IN_PROGRESS/APPLIED_PENDING_COMMIT/PROMOTED/
PROMOTION_FAILED/SUPERSEDED) refuse with KNOWLEDGE_GATE_CLOSED until
B3/K5 authorizes them. State changes happen ONLY through
`transition()` on validated records — no setter, no direct write —
so LLM output, provider results and retrieved notes cannot set state
(B1 S5 authority rule, enforced by construction: there is no other
write path in this module).
"""

from __future__ import annotations

from typing import Any

from .errors import KnowledgeError

PENDING = "PENDING"
IDENTITY_UNCONFIRMED = "IDENTITY_UNCONFIRMED"
NEEDS_SUPPORT = "NEEDS_SUPPORT"
REVIEWABLE = "REVIEWABLE"
CONFLICTING = "CONFLICTING"
DUPLICATE = "DUPLICATE"
APPROVED = "APPROVED"
PROMOTION_IN_PROGRESS = "PROMOTION_IN_PROGRESS"
APPLIED_PENDING_COMMIT = "APPLIED_PENDING_COMMIT"
PROMOTION_FAILED = "PROMOTION_FAILED"
PROMOTED = "PROMOTED"
REJECTED = "REJECTED"
SUPERSEDED = "SUPERSEDED"
RETRACTED = "RETRACTED"

STATES = frozenset({PENDING, IDENTITY_UNCONFIRMED, NEEDS_SUPPORT,
                    REVIEWABLE, CONFLICTING, DUPLICATE, APPROVED,
                    PROMOTION_IN_PROGRESS, APPLIED_PENDING_COMMIT,
                    PROMOTION_FAILED, PROMOTED, REJECTED, SUPERSEDED,
                    RETRACTED})

TERMINAL = frozenset({PROMOTED, REJECTED, SUPERSEDED, RETRACTED,
                      PROMOTION_FAILED})

GATED = frozenset({APPROVED, PROMOTION_IN_PROGRESS, APPLIED_PENDING_COMMIT,
                   PROMOTED, PROMOTION_FAILED, SUPERSEDED})

EDGES = {
    PENDING: {IDENTITY_UNCONFIRMED, REJECTED, RETRACTED},
    IDENTITY_UNCONFIRMED: {NEEDS_SUPPORT, REJECTED, RETRACTED},
    NEEDS_SUPPORT: {REVIEWABLE, REJECTED, RETRACTED},
    REVIEWABLE: {CONFLICTING, DUPLICATE, REJECTED, RETRACTED},
    CONFLICTING: {REVIEWABLE, DUPLICATE, REJECTED, RETRACTED},
    DUPLICATE: {REJECTED, RETRACTED},
    REJECTED: set(),
    RETRACTED: set(),
    PROMOTED: set(),
    SUPERSEDED: set(),
    PROMOTION_FAILED: set(),
    APPROVED: set(),
    PROMOTION_IN_PROGRESS: set(),
    APPLIED_PENDING_COMMIT: set(),
}


def transition(current: str, target: str) -> str:
    """One legal hop, or a refusal. Pure function over state names."""

    if current not in STATES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown state {current!r}")
    if target not in STATES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown state {target!r}")
    if target in GATED:
        raise KnowledgeError("KNOWLEDGE_GATE_CLOSED",
                             f"{target} needs B3/K5 authorization")
    if target not in EDGES[current]:
        raise KnowledgeError("KNOWLEDGE_ILLEGAL_STATE_TRANSITION",
                             f"illegal transition {current} -> {target}",
                             current=current, target=target)
    return target


def is_terminal(state: str) -> bool:
    return state in TERMINAL


__all__ = ["PENDING", "IDENTITY_UNCONFIRMED", "NEEDS_SUPPORT", "REVIEWABLE",
           "CONFLICTING", "DUPLICATE", "APPROVED", "PROMOTION_IN_PROGRESS",
           "APPLIED_PENDING_COMMIT", "PROMOTION_FAILED", "PROMOTED",
           "REJECTED", "SUPERSEDED", "RETRACTED", "STATES", "TERMINAL",
           "GATED", "EDGES", "transition", "is_terminal"]