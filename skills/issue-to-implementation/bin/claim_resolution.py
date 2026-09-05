#!/usr/bin/env python3
"""Deterministic claim resolution for GitHub Issues.

docs/GITHUB-WORKFLOW.md, "Multi-agent claims": GitHub Issue assignment is the
preferred claim; an explicit claim comment is the fallback for actors that
cannot assign. There is no lock service and no lock — GitHub state is the
claim, and this pure function decides who proceeds.

Decision table:
    0 claimants     -> CLAIM_FAILED   (nobody proceeds)
    1 claimant      -> that claimant proceeds
    >1 claimants    -> winner = min by (created_at, stable identifier)
                       ascending; every loser stops
    unorderable set -> CLAIM_CONFLICT (every claimant stops)

A signal is a dict: {"kind": "assignment"|"comment", "actor": str,
"created_at": ISO-8601 str, "identifier": stable GitHub id (comment or
assignment-event id)}.

Fail-closed policy for malformed signals: a signal without an actor or kind
is noise and is dropped, but a signal WITH an actor is evidence that someone
claimed — it is never silently discarded. Its claim simply cannot be ordered
(missing created_at, missing identifier, or identifier types differing
across signals), which makes the whole competing set indeterminate:
CLAIM_CONFLICT. Arbitration must never win by discarding a competitor.

The set must also be mutually orderable: two actors tying on both
(created_at, identifier) cannot be separated by any stable rule.

Usage:
    echo '[{...signals...}]' | python claim_resolution.py
    # -> {"status": "PROCEED", "winner": {...}, "losers": [...]}  (exit 0)
    # -> {"status": "CLAIM_FAILED"|"CLAIM_CONFLICT", ...}          (exit 1)
"""

from __future__ import annotations

import json
import sys

PROCEED = "PROCEED"
CLAIM_FAILED = "CLAIM_FAILED"
CLAIM_CONFLICT = "CLAIM_CONFLICT"

KINDS = ("assignment", "comment")
# The preferred form wins representation when one actor signalled twice.
_KIND_RANK = {"assignment": 0, "comment": 1}
# Sort placeholder so a missing timestamp loses to any real one when picking
# an actor's representative signal — never used for cross-actor ordering,
# which refuses instead.
_MISSING = "~"


class Claim:
    """One actor's normalized claim."""

    __slots__ = ("kind", "actor", "created_at", "identifier")

    def __init__(self, kind: str, actor: str, created_at, identifier) -> None:
        self.kind = kind
        self.actor = actor
        self.created_at = created_at
        self.identifier = identifier

    @property
    def orderable(self) -> bool:
        return bool(self.created_at) and self.identifier is not None \
            and not isinstance(self.identifier, (dict, list))

    @property
    def order_key(self):
        return (self.created_at, self.identifier)

    def to_record(self) -> dict:
        return {"kind": self.kind, "actor": self.actor,
                "created_at": self.created_at, "identifier": self.identifier}


def _claim_worthy(signal: dict) -> bool:
    """Evidence that someone claimed. Noise is dropped; claims are kept."""

    return (isinstance(signal, dict)
            and signal.get("kind") in KINDS
            and isinstance(signal.get("actor"), str)
            and bool(signal["actor"].strip()))


def normalize(signals) -> list[Claim]:
    """Collapse signals into one claim per actor, preferring the assignment.

    The same actor signalling twice is one claimant, not two; the assignment
    represents the actor when one exists, else the earliest comment. Signals
    without an actor or kind never reach here.
    """

    valid = [s for s in (signals or []) if _claim_worthy(s)]
    types = {type(s["identifier"]) for s in valid
             if s.get("identifier") is not None and not isinstance(s["identifier"], (dict, list))}
    if len(types) > 1:
        raise ValueError("identifier types differ across signals; "
                         "ordering would be arbitrary")
    by_actor: dict[str, list[dict]] = {}
    for signal in valid:
        by_actor.setdefault(signal["actor"].strip().lower(), []).append(signal)
    claims: list[Claim] = []
    for pool in by_actor.values():
        assignments = [s for s in pool if s["kind"] == "assignment"]
        candidates = assignments or pool
        representative = min(candidates, key=lambda s: (s.get("created_at") or _MISSING,
                                                        _KIND_RANK[s["kind"]],
                                                        str(s.get("identifier"))))
        claims.append(Claim(representative["kind"], representative["actor"].strip(),
                            representative.get("created_at"),
                            representative.get("identifier")))
    return claims


def resolve(signals) -> dict:
    """Verdict for the current claim state. Pure; no re-read happens here.

    The caller re-reads GitHub state before and after claiming (the skill
    owns that procedure); this function only makes the decision deterministic.
    """

    try:
        claims = normalize(signals)
    except ValueError as error:
        return {"status": CLAIM_CONFLICT, "winner": None,
                "losers": [], "reason": str(error)}
    if not claims:
        return {"status": CLAIM_FAILED, "winner": None, "losers": [],
                "reason": "no valid claim signal"}
    if len(claims) == 1:
        return {"status": PROCEED, "winner": claims[0].to_record(),
                "losers": [], "reason": "single claimant"}
    unorderable = [claim for claim in claims if not claim.orderable]
    if unorderable:
        return {"status": CLAIM_CONFLICT, "winner": None,
                "losers": [claim.to_record() for claim in claims],
                "reason": "a competing claim lacks created_at or a stable "
                          "identifier, so no winner can be chosen fairly"}
    keys = [claim.order_key for claim in claims]
    if len(set(map(repr, keys))) != len(keys):
        return {"status": CLAIM_CONFLICT, "winner": None,
                "losers": [claim.to_record() for claim in claims],
                "reason": "duplicate (created_at, identifier) ordering key"}
    ordered = sorted(claims, key=lambda claim: claim.order_key)
    return {"status": PROCEED, "winner": ordered[0].to_record(),
            "losers": [claim.to_record() for claim in ordered[1:]],
            "reason": "deterministic order: created_at, then identifier"}


def main(argv: list[str]) -> int:
    try:
        signals = json.load(sys.stdin)
    except ValueError as error:
        print(json.dumps({"status": CLAIM_CONFLICT, "winner": None, "losers": [],
                          "reason": f"unreadable input: {error}"}))
        return 1
    verdict = resolve(signals)
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["status"] == PROCEED else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))