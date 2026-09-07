"""Working memory: explicit, bounded, crash-safe operational state.

Transient plane only (ADR-0011): the active task, hypotheses, blockers
and next actions an agent needs across compaction or a crash. This is
operational continuity, not durable knowledge — nothing here is truth
(INV-04) and nothing here enters durable semantic retrieval (INV-03).

Crash model, mirroring `ainative/lifecycle/transaction.py`: every write
is an atomic replace, and the previous good copy is kept as a backup.
`load` never rewrites: a corrupt current plus a valid backup reports
RECOVERED and the caller persists it with `save`. Both corrupt fails
closed with KNOWLEDGE_STORE_CORRUPTED — never a fabricated state.
Stdlib only, per ADR-0009.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from . import store as storelib
from .candidate import TERMINAL
from .errors import KnowledgeError
from .provenance import now, observe_repository

SCHEMA_VERSION = 1

TRANSIENT_DIRNAME = Path(".ai-native") / "knowledge" / "transient"
WORKING_FILE = "working.json"
BACKUP_FILE = "working.backup.json"
CHECKPOINTS_DIRNAME = "checkpoints"

MAX_CHECKPOINTS = 10
MAX_CHECKPOINT_AGE_DAYS = 30

MAX_TEXT_CHARS = 4000
MAX_ITEM_CHARS = 1000
MAX_LIST_ITEMS = 200

EMPTY = "empty"
CURRENT = "current"
RECOVERED = "recovered"
EXPIRED = "expired"

RESTORED = "restored"
RESTORE_REQUIRES_RECONCILIATION = "restore_requires_reconciliation"

_CHECKPOINT_ID = re.compile(r"^ckpt_[0-9a-f]{32}$")


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"working.{name} is not a string")
    if len(value) > MAX_TEXT_CHARS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"working.{name} exceeds {MAX_TEXT_CHARS} chars")
    return value


def _strlist(name: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"working.{name} is not a string list")
    if len(value) > MAX_LIST_ITEMS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"working.{name} exceeds {MAX_LIST_ITEMS} items")
    for item in value:
        if len(item) > MAX_ITEM_CHARS:
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 f"working.{name} item exceeds {MAX_ITEM_CHARS} chars")
    return list(value)


@dataclass
class WorkingState:
    """Operational state only: what to do next, not what is true."""

    task: str = ""
    goal: str = ""
    plan: str = ""
    files_touched: list[str] = field(default_factory=list)
    current_hypotheses: list[str] = field(default_factory=list)
    confirmed_findings: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    test_results: str = ""
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    candidate_ids: list[str] = field(default_factory=list)
    repository_head: str | None = None
    updated_at: str = ""
    expires_at: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, raw: Any) -> "WorkingState":
        if not isinstance(raw, dict):
            raise KnowledgeError("KNOWLEDGE_MALFORMED", "working state is not an object")
        version = raw.get("schema_version")
        if version != SCHEMA_VERSION:
            raise KnowledgeError("KNOWLEDGE_SCHEMA_UNKNOWN",
                                 f"working schema_version {version!r} is not supported "
                                 f"(reader understands {SCHEMA_VERSION})")
        return cls(
            task=_text("task", raw.get("task", "")),
            goal=_text("goal", raw.get("goal", "")),
            plan=_text("plan", raw.get("plan", "")),
            files_touched=_strlist("files_touched", raw.get("files_touched", [])),
            current_hypotheses=_strlist("current_hypotheses", raw.get("current_hypotheses", [])),
            confirmed_findings=_strlist("confirmed_findings", raw.get("confirmed_findings", [])),
            open_questions=_strlist("open_questions", raw.get("open_questions", [])),
            tests_run=_strlist("tests_run", raw.get("tests_run", [])),
            test_results=_text("test_results", raw.get("test_results", "")),
            blockers=_strlist("blockers", raw.get("blockers", [])),
            next_action=_text("next_action", raw.get("next_action", "")),
            candidate_ids=_strlist("candidate_ids", raw.get("candidate_ids", [])),
            repository_head=raw.get("repository_head"),
            updated_at=str(raw.get("updated_at", "")),
            expires_at=raw.get("expires_at"),
            schema_version=SCHEMA_VERSION,
        )


def transient_dir(project: Path) -> Path:
    return Path(project) / TRANSIENT_DIRNAME


def working_path(project: Path) -> Path:
    return transient_dir(project) / WORKING_FILE


def backup_path(project: Path) -> Path:
    return transient_dir(project) / BACKUP_FILE


def checkpoints_dir(project: Path) -> Path:
    return transient_dir(project) / CHECKPOINTS_DIRNAME


def _try_read(path: Path) -> WorkingState | None:
    """A stored state, or None when missing or unreadable. Never raises that."""

    if not path.is_file():
        return None
    try:
        return WorkingState.from_record(json.loads(path.read_text(encoding="utf-8")))
    except KnowledgeError as error:
        if error.code == "KNOWLEDGE_SCHEMA_UNKNOWN":
            raise
        return None
    except (OSError, ValueError):
        return None


def save(project: Path, state: WorkingState) -> WorkingState:
    """Validate, stamp and persist. The previous good copy becomes the backup."""

    state.updated_at = now()
    validated = WorkingState.from_record(state.to_record())
    current = working_path(project)
    previous = current.read_bytes() if current.is_file() else None
    if previous is not None:
        try:
            WorkingState.from_record(json.loads(previous.decode("utf-8")))
        except (KnowledgeError, ValueError, UnicodeDecodeError):
            previous = None
    statelib.write_atomic(current, json.dumps(validated.to_record(), indent=2,
                                              sort_keys=True) + "\n")
    if previous is not None:
        statelib.write_bytes_atomic(backup_path(project), previous)
    return validated


def load(project: Path) -> tuple[WorkingState | None, str]:
    """Read without writing. A corrupt current falls back to the backup."""

    state = _try_read(working_path(project))
    if state is not None:
        if state.expires_at is not None and state.expires_at <= now():
            return state, EXPIRED
        return state, CURRENT
    if not working_path(project).is_file() and not backup_path(project).is_file():
        return None, EMPTY
    backup = _try_read(backup_path(project))
    if backup is None:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             "working state and backup are both unreadable; "
                             "refusing to fabricate one")
    return backup, RECOVERED


def pending_candidate_ids(project: Path) -> list[str]:
    """Non-terminal candidates worth carrying across compaction."""

    try:
        records = storelib.read_all(project)
    except KnowledgeError:
        return []
    return [item["candidate_id"] for item in records if item["status"] not in TERMINAL]


def checkpoint(project: Path, *, reason: str = "manual") -> dict[str, Any]:
    """Freeze operational state plus repo head. Never dumps raw reasoning."""

    if not isinstance(reason, str) or not reason.strip() or len(reason) > 200:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "checkpoint reason must be 1..200 chars")
    state, _ = load(project)
    if state is None:
        raise KnowledgeError("KNOWLEDGE_NOT_FOUND", "nothing to checkpoint")
    observed = observe_repository(project)
    record = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": statelib.new_identifier("ckpt"),
        "reason": reason,
        "created_at": now(),
        "repository_head": observed.get("git_head"),
        "git_dirty": observed.get("git_dirty"),
        "pending_candidate_ids": pending_candidate_ids(project),
        "working": state.to_record(),
    }
    path = checkpoints_dir(project) / f"{record['checkpoint_id']}.json"
    statelib.write_atomic(path, json.dumps(record, indent=2, sort_keys=True) + "\n")
    record["pruned"] = prune_checkpoints(project)
    return record


def _read_checkpoint(project: Path, checkpoint_id: str) -> dict[str, Any]:
    if not _CHECKPOINT_ID.match(checkpoint_id):
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"illegal checkpoint id {checkpoint_id!r}")
    path = checkpoints_dir(project) / f"{checkpoint_id}.json"
    if not path.is_file():
        raise KnowledgeError("KNOWLEDGE_NOT_FOUND",
                             f"unknown checkpoint {checkpoint_id!r}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"checkpoint {checkpoint_id!r} is unreadable: {error}") from error
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"checkpoint {checkpoint_id!r} has an unsupported schema")
    return record


def describe_restore(project: Path, checkpoint_id: str) -> tuple[dict[str, Any], str]:
    """Validate a checkpoint and compare heads. Reads only, never writes."""

    record = _read_checkpoint(project, checkpoint_id)
    WorkingState.from_record(record["working"])
    recorded_head = record.get("repository_head")
    observed_head = observe_repository(project).get("git_head")
    if recorded_head is not None and recorded_head != observed_head:
        return record, RESTORE_REQUIRES_RECONCILIATION
    return record, RESTORED


def restore(project: Path, checkpoint_id: str) -> tuple[dict[str, Any], str]:
    """Bring back frozen state, flagging a moved repository underneath."""

    record, status = describe_restore(project, checkpoint_id)
    save(project, WorkingState.from_record(record["working"]))
    return record, status


def list_checkpoints(project: Path) -> list[dict[str, Any]]:
    """Newest first. Unreadable entries fail closed like everything else."""

    directory = checkpoints_dir(project)
    if not directory.is_dir():
        return []
    records = []
    for path in sorted(directory.glob("ckpt_*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                                 f"checkpoint {path.name} is unreadable: {error}") from error
        records.append(record)
    return sorted(records, key=lambda item: str(item.get("created_at", "")), reverse=True)


def prune_checkpoints(project: Path) -> list[str]:
    """Enforce count plus age bounds. Returns dropped checkpoint ids."""

    records = list_checkpoints(project)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_CHECKPOINT_AGE_DAYS)).isoformat()
    keep = [item for item in records if str(item.get("created_at", "")) >= cutoff][:MAX_CHECKPOINTS]
    keep_ids = {item["checkpoint_id"] for item in keep}
    dropped = []
    for item in records:
        if item["checkpoint_id"] not in keep_ids:
            (checkpoints_dir(project) / f"{item['checkpoint_id']}.json").unlink(missing_ok=True)
            dropped.append(item["checkpoint_id"])
    return sorted(dropped)


def clear(project: Path) -> list[str]:
    """Discard transient state. Safe by plane: canonical knowledge untouched."""

    removed = []
    for path in [working_path(project), backup_path(project)]:
        if path.is_file():
            path.unlink()
            removed.append(path.name)
    directory = checkpoints_dir(project)
    if directory.is_dir():
        for path in sorted(directory.glob("ckpt_*.json")):
            path.unlink()
            removed.append(f"checkpoints/{path.name}")
    return sorted(removed)


__all__ = ["SCHEMA_VERSION", "TRANSIENT_DIRNAME", "WORKING_FILE", "BACKUP_FILE",
           "CHECKPOINTS_DIRNAME", "MAX_CHECKPOINTS", "MAX_CHECKPOINT_AGE_DAYS",
           "MAX_TEXT_CHARS", "MAX_ITEM_CHARS", "MAX_LIST_ITEMS",
           "EMPTY", "CURRENT", "RECOVERED", "EXPIRED",
           "RESTORED", "RESTORE_REQUIRES_RECONCILIATION",
           "WorkingState", "transient_dir", "working_path", "backup_path",
           "checkpoints_dir", "save", "load", "pending_candidate_ids",
           "checkpoint", "describe_restore", "restore", "list_checkpoints", "prune_checkpoints", "clear"]