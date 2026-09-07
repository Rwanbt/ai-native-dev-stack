"""Candidate store: append-only JSONL under `.ai-native/knowledge/`.

File-based first, SQLite deferred (ADR-0011 section 4). This file holds
candidate and state metadata ONLY — reading it as project truth is a P0
violation (INV-06). Every write goes through an atomic replace
(`statelib.write_atomic`); every state change appends an audit event.
Optimistic concurrency for promotion (`base_digest` checks) arrives in
Phase K4; until then `set_status` is last-writer-wins on the file, which
is safe because K1 never touches canonical targets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from .candidate import validate_candidate
from .errors import KnowledgeError
from .provenance import now

KNOWLEDGE_DIRNAME = Path(".ai-native") / "knowledge"
CANDIDATES_FILE = "candidates.jsonl"
AUDIT_FILE = "audit.jsonl"

# Bounded growth is a P0 gate (KNOWLEDGE-SECURITY.md section 7): the
# store refuses to grow past these, forcing consolidation or export.
MAX_CANDIDATES = 1000
MAX_AUDIT_EVENTS = 5000


def knowledge_dir(project: Path) -> Path:
    return Path(project) / KNOWLEDGE_DIRNAME


def candidates_path(project: Path) -> Path:
    return knowledge_dir(project) / CANDIDATES_FILE


def audit_path(project: Path) -> Path:
    return knowledge_dir(project) / AUDIT_FILE


def _read_lines(path: Path, what: str) -> list[str]:
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"cannot read {path}: {error}") from error


def _parse_line(line: str, number: int) -> dict:
    try:
        record = json.loads(line)
    except ValueError as error:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"line {number} is not JSON: {error}") from error
    return validate_candidate(record)


def read_all(project: Path) -> list[dict]:
    """Every stored candidate, validated. Corrupt lines fail closed."""

    return _parse_line_list(_read_lines(candidates_path(project), "candidates"))


def _parse_line_list(lines: list[str]) -> list[dict]:
    return [_parse_line(line, number) for number, line in enumerate(lines, 1)
            if line.strip()]


def _write_all(project: Path, records: list[dict]) -> None:
    if len(records) > MAX_CANDIDATES:
        raise KnowledgeError("KNOWLEDGE_CONFLICT",
                             f"candidate store full ({len(records)} > "
                             f"{MAX_CANDIDATES}); consolidate or export first")
    payload = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    statelib.write_atomic(candidates_path(project), payload)


def append(project: Path, record: dict) -> dict:
    """Validate, secret-scan and persist one candidate. Returns the record."""

    candidate = validate_candidate(record)
    records = read_all(project)
    if any(item["candidate_id"] == candidate["candidate_id"] for item in records):
        raise KnowledgeError("KNOWLEDGE_DUPLICATE_ID",
                             f"candidate {candidate['candidate_id']} already stored")
    records.append(candidate)
    _write_all(project, records)
    record_audit(project, candidate_id=candidate["candidate_id"],
                 operation="CAPTURE", detail={"status": candidate["status"]},
                 actor=candidate["provenance"].get("agent", "unknown"))
    return candidate


def list_candidates(project: Path, *, status: str | None = None,
                    kind: str | None = None) -> list[dict]:
    records = read_all(project)
    if status is not None:
        records = [item for item in records if item["status"] == status]
    if kind is not None:
        records = [item for item in records if item["kind"] == kind]
    return records


def inspect_candidate(project: Path, candidate_id: str) -> dict:
    for item in read_all(project):
        if item["candidate_id"] == candidate_id:
            return item
    raise KnowledgeError("KNOWLEDGE_NOT_FOUND", f"unknown candidate {candidate_id!r}")


def update_record(project: Path, candidate_id: str, new_record: dict, *,
                  operation: str, detail: dict | None = None,
                  actor: str = "unknown") -> dict:
    """Validate, swap and audit one candidate. Field edits go through here."""

    validated = validate_candidate(new_record)
    records = read_all(project)
    for index, item in enumerate(records):
        if item["candidate_id"] == candidate_id:
            records[index] = validated
            _write_all(project, records)
            record_audit(project, candidate_id=candidate_id,
                         operation=operation,
                         detail=detail or {},
                         actor=actor)
            return validated
    raise KnowledgeError("KNOWLEDGE_NOT_FOUND", f"unknown candidate {candidate_id!r}")


def set_status(project: Path, candidate_id: str, to_status: str,
               *, actor: str) -> dict:
    """Apply a state-machine transition and audit it. Pure transition rules."""

    from .candidate import transition as apply_transition

    current = inspect_candidate(project, candidate_id)
    updated = apply_transition(current, to_status)
    return update_record(project, candidate_id, updated,
                         operation="TRANSITION",
                         detail={"from": current["status"], "to": to_status},
                         actor=actor)


def record_audit(project: Path, *, candidate_id: str, operation: str,
                 detail: dict[str, Any] | None = None,
                 actor: str = "unknown") -> dict:
    """Append one audit event. Lifecycle metadata, never knowledge (INV-06)."""

    event = {"event_id": statelib.new_identifier("kev"),
             "candidate_id": candidate_id, "operation": operation,
             "detail": detail or {}, "actor": actor, "timestamp": now()}
    path = audit_path(project)
    lines = _read_lines(path, "audit")
    lines.append(json.dumps(event, sort_keys=True))
    if len(lines) > MAX_AUDIT_EVENTS:
        raise KnowledgeError("KNOWLEDGE_CONFLICT",
                             f"audit log full ({len(lines)} > {MAX_AUDIT_EVENTS}); "
                             "export and rotate first")
    statelib.write_atomic(path, "".join(line + "\n" for line in lines))
    return event


def export(project: Path) -> dict:
    """Full candidate plus audit dump for backup or rotation. Read-only."""

    from .provenance import now
    return {"exported_at": now(), "candidates": read_all(Path(project)),
            "audit": read_audit(Path(project))}


def read_audit(project: Path) -> list[dict]:
    events: list[dict] = []
    for number, line in enumerate(_read_lines(audit_path(project), "audit"), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError as error:
            raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                                 f"audit line {number} is not JSON: {error}") from error
    return events


__all__ = ["KNOWLEDGE_DIRNAME", "CANDIDATES_FILE", "AUDIT_FILE",
           "MAX_CANDIDATES", "MAX_AUDIT_EVENTS", "knowledge_dir",
           "candidates_path", "audit_path", "read_all", "append",
           "list_candidates", "inspect_candidate", "update_record", "set_status",
           "record_audit", "read_audit", "export"]