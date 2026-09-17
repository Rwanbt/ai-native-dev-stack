"""Canonical claim identities, and the durable journal that survives a crash.

A claim is a remote mutation: an agent asks a work authority to recognize it
as the owner of a WorkItem. What makes a crash recoverable is that the local
record of the attempt exists *before* the remote POST — journal first, then
exactly one POST, then a re-read that searches for the attempt's own marker
(ADR-0018 sections 3–6).

This module owns the local half: canonical identities, UTC-normalized
ordering, the PENDING → outcome journal under `.ai-native/state/claim-attempts/`,
and the explicit operator transitions. It never calls a provider API, never
holds a credential, and never infers an outcome: the harness observes, this
module records and arbitrates deterministically.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .lifecycle import state as statelib
from .lifecycle.errors import LifecycleError

KIND_COMMENT = "comment"
KIND_NOTE = "note"
KIND_ASSIGNMENT = "assignment"
EVENT_KINDS = (KIND_COMMENT, KIND_NOTE, KIND_ASSIGNMENT)

PENDING = "PENDING"
CONFIRMED = "CONFIRMED"
LOST = "LOST"
CONFLICT = "CONFLICT"
UNCERTAIN = "UNCERTAIN"
ABANDONED = "ABANDONED"
OUTCOMES = (CONFIRMED, LOST, CONFLICT, UNCERTAIN, ABANDONED)
UNRESOLVED = (PENDING, UNCERTAIN)

ATTEMPTS_RELATIVE = Path(".ai-native") / "state" / "claim-attempts"
MARKER_PREFIX = "ainative-claim-attempt:"

_ATTEMPT_ID = re.compile(r"^claim_[0-9a-f]{32}$")
_TOKEN = re.compile(r"^[^\s:]+$")


def _token(value: str, what: str) -> str:
    if not isinstance(value, str) or not _TOKEN.match(value):
        raise LifecycleError("CLAIM_INVALID",
                             f"a claim {what} must be a non-empty token without "
                             f"whitespace or ':', got {value!r}")
    return value


def principal(provider: str, stable_id: str) -> str:
    """`<provider>:principal:<stable-provider-id>` — who is claiming."""

    return f"{_token(provider, 'provider')}:principal:{_token(stable_id, 'principal id')}"


def event_identifier(provider: str, kind: str, stable_id: str) -> str:
    """`<provider>:<event-kind>:<stable-event-id>` — which claim event it is."""

    if kind not in EVENT_KINDS:
        raise LifecycleError("CLAIM_INVALID",
                             f"unknown claim event kind {kind!r} "
                             f"(known: {', '.join(EVENT_KINDS)})")
    return f"{_token(provider, 'provider')}:{kind}:{_token(stable_id, 'event id')}"


def to_utc(value: str) -> str:
    """An ISO-8601 timestamp normalized to UTC. A naive one is refused.

    Ordering claims by timestamp is only deterministic if every timestamp
    carries its zone; "2026-09-16T10:00:00" cannot be compared with
    "2026-09-16T09:00:00+02:00" without guessing.
    """

    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise LifecycleError("CLAIM_INVALID",
                             f"claim timestamp {value!r} is not ISO-8601") from error
    if moment.tzinfo is None:
        raise LifecycleError("CLAIM_INVALID",
                             f"claim timestamp {value!r} carries no timezone")
    return moment.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class ClaimEvent:
    """One observed claim signal, in canonical form."""

    identifier: str          # canonical event identifier
    created_at: str          # UTC ISO-8601
    actor: str               # canonical principal

    def sort_key(self) -> tuple[str, str]:
        return (self.created_at, self.identifier)

    def to_record(self) -> dict:
        return {"identifier": self.identifier, "created_at": self.created_at,
                "actor": self.actor}


def winner(events) -> ClaimEvent | None:
    """The winning claim by `(created_at_utc, canonical_event_identifier)`.

    Exact duplicates are one event. Two distinct events with the same key — a
    duplicate identifier carrying different actors — are unorderable and refuse
    as `CLAIM_CONFLICT`: every claimant stops (ADR-0018 section 3).
    """

    unique: dict[str, ClaimEvent] = {}
    for event in events:
        existing = unique.get(event.identifier)
        if existing is None:
            unique[event.identifier] = event
        elif existing != event:
            raise LifecycleError(
                "CLAIM_CONFLICT",
                f"two different claim events share the identifier "
                f"{event.identifier!r}; they cannot be ordered",
                identifier=event.identifier)
    if not unique:
        return None
    ordered = sorted(unique.values(), key=ClaimEvent.sort_key)
    if len(ordered) > 1 and ordered[0].sort_key() == ordered[1].sort_key():
        raise LifecycleError("CLAIM_CONFLICT",
                             "two claim events are unorderable: identical "
                             "timestamp and identifier")
    return ordered[0]


@dataclass
class ClaimAttempt:
    """One journaled attempt to claim a WorkItem."""

    attempt_id: str
    authority: dict                  # WorkAuthorityRef.to_record()
    item: str                        # the WorkItem identifier on that authority
    principal: str                   # canonical principal
    marker: str                      # exact marker the remote signal must carry
    state: str = PENDING
    created_at: str = ""
    outcome_at: str | None = None
    note: str = ""
    history: list = field(default_factory=list)

    def to_record(self) -> dict:
        return {"attempt_id": self.attempt_id, "authority": dict(self.authority),
                "item": self.item, "principal": self.principal, "marker": self.marker,
                "state": self.state, "created_at": self.created_at,
                "outcome_at": self.outcome_at, "note": self.note,
                "history": list(self.history)}

    @classmethod
    def from_record(cls, raw: object) -> "ClaimAttempt":
        if not isinstance(raw, dict):
            raise LifecycleError("CLAIM_JOURNAL_UNAVAILABLE",
                                 "a claim attempt record is not an object")
        attempt_id = raw.get("attempt_id")
        if not isinstance(attempt_id, str) or not _ATTEMPT_ID.match(attempt_id):
            raise LifecycleError("CLAIM_JOURNAL_UNAVAILABLE",
                                 "a claim attempt record carries an invalid id")
        if not isinstance(raw.get("authority"), dict) or not isinstance(raw.get("item"), str):
            raise LifecycleError("CLAIM_JOURNAL_UNAVAILABLE",
                                 f"claim attempt {attempt_id} is malformed")
        if not isinstance(raw.get("principal"), str) or not isinstance(raw.get("marker"), str):
            raise LifecycleError("CLAIM_JOURNAL_UNAVAILABLE",
                                 f"claim attempt {attempt_id} is malformed")
        state = raw.get("state")
        if state not in (PENDING, *OUTCOMES):
            raise LifecycleError("CLAIM_JOURNAL_UNAVAILABLE",
                                 f"claim attempt {attempt_id} carries an unknown state "
                                 f"{state!r}")
        return cls(attempt_id=attempt_id, authority=dict(raw["authority"]),
                   item=raw["item"], principal=raw["principal"], marker=raw["marker"],
                   state=state, created_at=str(raw.get("created_at") or ""),
                   outcome_at=raw.get("outcome_at"), note=str(raw.get("note") or ""),
                   history=list(raw.get("history") or []))


def attempts_root(project: Path) -> Path:
    return Path(project) / ATTEMPTS_RELATIVE


def new_attempt(*, authority, item: str, principal: str, note: str = "") -> ClaimAttempt:
    """A fresh attempt with its deterministic remote marker. Not yet journaled."""

    attempt_id = statelib.new_identifier("claim")
    return ClaimAttempt(attempt_id=attempt_id, authority=authority.to_record(),
                        item=_token(item, "item"), principal=principal,
                        marker=f"{MARKER_PREFIX}{attempt_id}", note=note)


def _path(project: Path, attempt_id: str) -> Path:
    if not isinstance(attempt_id, str) or not _ATTEMPT_ID.match(attempt_id):
        raise LifecycleError("CLAIM_INVALID",
                             f"invalid claim attempt id {attempt_id!r}")
    return attempts_root(project) / f"{attempt_id}.json"


def _write(project: Path, attempt: ClaimAttempt) -> None:
    """One durable write of an attempt record, or a fail-closed refusal."""

    path = _path(project, attempt.attempt_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        statelib.write_atomic(path, json.dumps(attempt.to_record(), indent=2,
                                               sort_keys=True) + "\n")
    except OSError as error:
        raise LifecycleError(
            "CLAIM_JOURNAL_UNAVAILABLE",
            f"cannot write the claim journal at {path}: {error}") from error


def begin(project: Path, attempt: ClaimAttempt) -> Path:
    """Write the PENDING attempt durably. This happens BEFORE the remote POST.

    A local write that fails is `CLAIM_JOURNAL_UNAVAILABLE` and the caller
    must not POST at all: an attempt nobody recorded cannot be recovered.
    """

    attempt.state = PENDING
    attempt.created_at = attempt.created_at or statelib.now()
    attempt.history.append({"state": PENDING, "at": attempt.created_at})
    _write(project, attempt)
    return _path(project, attempt.attempt_id)


def load_attempt(project: Path, attempt_id: str) -> ClaimAttempt:
    path = _path(project, attempt_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise LifecycleError("CLAIM_JOURNAL_UNAVAILABLE",
                             f"no claim attempt {attempt_id!r} is journaled") from error
    except (OSError, ValueError) as error:
        raise LifecycleError(
            "CLAIM_JOURNAL_UNAVAILABLE",
            f"claim attempt {attempt_id!r} is unreadable; nothing may infer "
            f"its outcome: {error}") from error
    return ClaimAttempt.from_record(payload)


def list_attempts(project: Path) -> list[ClaimAttempt]:
    """Every journaled attempt, or a refusal — a corrupt journal is never skipped.

    An unreadable entry might be the one that says a POST is in flight; listing
    the others and pretending it is not there is how a second POST happens.
    """

    root = attempts_root(project)
    if not root.is_dir():
        return []
    attempts: list[ClaimAttempt] = []
    for path in sorted(root.glob("*.json")):
        attempts.append(load_attempt(project, path.stem))
    return attempts


def unresolved(project: Path) -> list[ClaimAttempt]:
    return [attempt for attempt in list_attempts(project)
            if attempt.state in UNRESOLVED]


def record_outcome(project: Path, attempt_id: str, outcome: str, *, note: str = "") -> ClaimAttempt:
    """Persist what the re-read proved. Never invents an outcome."""

    if outcome not in OUTCOMES:
        raise LifecycleError("CLAIM_INVALID",
                             f"unknown claim outcome {outcome!r} "
                             f"(known: {', '.join(OUTCOMES)})")
    attempt = load_attempt(project, attempt_id)
    if attempt.state == ABANDONED:
        raise LifecycleError("CLAIM_INVALID",
                             f"attempt {attempt_id} was abandoned; its record is final "
                             "(abandonment is an operator decision, not a retry slot)")
    attempt.state = outcome
    attempt.outcome_at = statelib.now()
    if note:
        attempt.note = f"{attempt.note}\n{note}".strip()
    attempt.history.append({"state": outcome, "at": attempt.outcome_at})
    _write(project, attempt)
    return attempt


def abandon(project: Path, attempt_id: str, *, confirm: bool) -> ClaimAttempt:
    """The explicit operator transition. Local only; the record is retained.

    Only an unresolved attempt (PENDING or UNCERTAIN) can be abandoned: a
    CONFIRMED claim is real on the remote, and hiding it locally would not
    release it. After abandonment a new attempt is allowed.
    """

    if not confirm:
        raise LifecycleError("CONFIRMATION_REQUIRED",
                             "abandoning a claim attempt is an explicit operator "
                             "decision; pass --confirm after inspecting the remote state")
    attempt = load_attempt(project, attempt_id)
    if attempt.state not in UNRESOLVED:
        raise LifecycleError("CLAIM_INVALID",
                             f"attempt {attempt_id} is {attempt.state}; only an "
                             "unresolved attempt can be abandoned")
    attempt.state = ABANDONED
    attempt.outcome_at = statelib.now()
    attempt.history.append({"state": ABANDONED, "at": attempt.outcome_at})
    _write(project, attempt)
    return attempt


__all__ = [
    "KIND_COMMENT", "KIND_NOTE", "KIND_ASSIGNMENT", "EVENT_KINDS",
    "PENDING", "CONFIRMED", "LOST", "CONFLICT", "UNCERTAIN", "ABANDONED",
    "OUTCOMES", "UNRESOLVED", "ATTEMPTS_RELATIVE", "MARKER_PREFIX",
    "principal", "event_identifier", "to_utc", "ClaimEvent", "winner",
    "ClaimAttempt", "attempts_root", "new_attempt", "begin", "load_attempt",
    "list_attempts", "unresolved", "record_outcome", "abandon",
]
