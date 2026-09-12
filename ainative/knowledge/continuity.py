"""Working continuity: checkpoints bound to repository state (PR10).

A checkpoint freezes operational state (task, next action, files
touched, open work, hypotheses, findings, questions, blockers, tests
run, candidate ids) together with the Git HEAD, a dirty-tree fingerprint
and a diff digest. Restore compares all three: same HEAD plus same
fingerprint restores cleanly; same HEAD with a changed tree reports
RESTORE_DIRTY_TREE_DIVERGENCE instead of pretending continuity; a
moved HEAD reports STALE_HEAD; past TTL reports EXPIRED. Records use
a fixed schema — unknown fields (including any chain-of-thought
payload) are refused structurally, and free text is quarantined like
any untrusted persistence. Storage lives under Local Control
(transient working state, purgeable); recovery is atomic replace plus
the shared project guard, never a second engine.
"""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib
from ainative.lifecycle.lock import project_guard

from . import paths as controlpaths
from . import quarantine as quarantinelib
from .errors import KnowledgeError

WORKING_DIRNAME = "working"
MAX_CHECKPOINT_BYTES = 64 * 1024
MAX_CHECKPOINTS = 10
MAX_DIFF_BYTES = 1024 * 1024
MAX_LIST_ITEMS = 100
MAX_TEXT_CHARS = 2000

RESTORED = "RESTORED"
DIVERGENCE = "RESTORE_DIRTY_TREE_DIVERGENCE"
STALE_HEAD = "STALE_HEAD"
EXPIRED = "EXPIRED"
MISSING = "MISSING"

FIELDS = frozenset({"task", "files_touched", "open_work", "blockers",
                    "tests_run", "next_action", "hypotheses", "findings",
                    "questions", "candidate_ids"})


def _git(project: Path, *args: str, timeout: int = 10):
    try:
        return subprocess.run(["git", "-C", str(project), *args],
                              capture_output=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _git_text(project: Path, *args: str) -> str | None:
    result = _git(project, *args)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def repository_snapshot(project: Path) -> dict[str, Any]:
    """HEAD, dirty fingerprint and diff digest. Best-effort, never raises."""

    head_out = _git_text(project, "rev-parse", "HEAD")
    status_out = _git_text(project, "status", "--porcelain")
    snapshot: dict[str, Any] = {"git_head": head_out.strip() if head_out else None,
                                "dirty_fingerprint": None, "diff_digest": None,
                                "diff_truncated": False, "git_available": False}
    if head_out is None or status_out is None:
        return snapshot
    snapshot["git_available"] = True
    snapshot["dirty_fingerprint"] = sha256(
        "\n".join(sorted(status_out.splitlines())).encode("utf-8")).hexdigest()
    diff = _git(project, "diff", "HEAD", "--", ".")
    if diff is None or diff.returncode != 0:
        return snapshot
    raw = diff.stdout or b""
    if len(raw) > MAX_DIFF_BYTES:
        raw = raw[:MAX_DIFF_BYTES]
        snapshot["diff_truncated"] = True
    snapshot["diff_digest"] = sha256(raw).hexdigest()
    return snapshot


def _bounded_list(name: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"{name} must be a list")
    if len(value) > MAX_LIST_ITEMS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"{name} too many items")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 f"{name} holds text items only")
        if len(item) > MAX_TEXT_CHARS:
            raise KnowledgeError("KNOWLEDGE_MALFORMED", f"{name} item too long")
    return list(value)


def validate_state(raw: Any) -> dict[str, Any]:
    """Fixed operational schema. Unknown fields refused (no CoT smuggling)."""

    if not isinstance(raw, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "working state not an object")
    unknown = set(raw) - FIELDS
    if unknown:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "working state holds fixed fields only")
    task = raw.get("task", "")
    if not isinstance(task, str) or not task.strip() or len(task) > MAX_TEXT_CHARS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "task must be short text")
    next_action = raw.get("next_action", "")
    if not isinstance(next_action, str) or len(next_action) > MAX_TEXT_CHARS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "next_action must be short text")
    state = {"task": task,
             "files_touched": _bounded_list("files_touched",
                                            raw.get("files_touched", [])),
             "open_work": _bounded_list("open_work", raw.get("open_work", [])),
             "blockers": _bounded_list("blockers", raw.get("blockers", [])),
             "tests_run": _bounded_list("tests_run", raw.get("tests_run", [])),
             "next_action": next_action,
             "hypotheses": _bounded_list("hypotheses", raw.get("hypotheses", [])),
             "findings": _bounded_list("findings", raw.get("findings", [])),
             "questions": _bounded_list("questions", raw.get("questions", [])),
             "candidate_ids": _bounded_list("candidate_ids",
                                            raw.get("candidate_ids", []))}
    quarantinelib.check(task, next_action, *state["files_touched"],
                        *state["open_work"], *state["blockers"],
                        *state["tests_run"], *state["hypotheses"],
                        *state["findings"], *state["questions"],
                        *state["candidate_ids"], purpose="working state")
    return state


def _working_dir(project: Path) -> Path:
    return controlpaths.state_dir(Path(project)) / WORKING_DIRNAME


def checkpoint(project: Path, state: dict, *, ttl_seconds: int = 86400) -> dict[str, Any]:
    """Freeze operational state with repository snapshot. Guarded write."""

    validated = validate_state(state)
    root = Path(project)
    controlpaths.require_policy(root)
    controlpaths.ensure_contained(root)
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError) as error:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "ttl must be an integer") from error

    def _run() -> dict:
        directory = _working_dir(root)
        directory.mkdir(parents=True, exist_ok=True)
        def _age(path: Path) -> tuple:
            try:
                return (path.stat().st_mtime_ns, path.name)
            except OSError:
                return (0, path.name)

        existing = sorted(directory.glob("ckpt_*.json"), key=_age)
        while len(existing) >= MAX_CHECKPOINTS:
            oldest = existing.pop(0)
            try:
                oldest.unlink(missing_ok=True)
            except OSError:
                break
        record = {"schema_version": 1,
                  "checkpoint_id": statelib.new_identifier("ckpt"),
                  "created_at": statelib.now(), "ttl_seconds": ttl,
                  "repository": repository_snapshot(root),
                  "state": validated}
        payload = json.dumps(record, sort_keys=True) + "\n"
        if len(payload.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
            raise KnowledgeError("KNOWLEDGE_CANDIDATE_TOO_LARGE",
                                 "checkpoint exceeds size bound")
        statelib.write_atomic(directory / f"{record['checkpoint_id']}.json",
                              payload)
        return record

    with project_guard(root):
        return _run()


def _read_checkpoint(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"{path.name} unreadable") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"{path.name} unsupported schema")
    return raw


def _expired(record: dict) -> bool:
    from datetime import datetime, timedelta, timezone
    try:
        created = datetime.fromisoformat(record.get("created_at", ""))
        ttl = int(record.get("ttl_seconds", 0))
    except (TypeError, ValueError) as error:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             "checkpoint clock fields unreadable") from error
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > created + timedelta(seconds=ttl)


def restore(project: Path, checkpoint_id: str) -> dict[str, Any]:
    """Restore with explicit divergence accounting. Read-only."""

    root = Path(project)
    controlpaths.ensure_contained(root)
    path = _working_dir(root) / f"{checkpoint_id}.json"
    if not path.is_file():
        return {"status": MISSING, "state": None}
    record = _read_checkpoint(path)
    if _expired(record):
        return {"status": EXPIRED, "state": record["state"]}
    current = repository_snapshot(root)
    saved = record.get("repository", {})
    if saved.get("git_head") != current.get("git_head"):
        return {"status": STALE_HEAD, "state": record["state"]}
    if saved.get("dirty_fingerprint") != current.get("dirty_fingerprint"):
        return {"status": DIVERGENCE, "state": record["state"]}
    return {"status": RESTORED, "state": record["state"]}


def list_checkpoints(project: Path) -> list[dict[str, Any]]:
    """Newest first. Corrupt entries fail closed like all readers."""

    root = Path(project)
    controlpaths.ensure_contained(root)
    directory = _working_dir(root)
    if not directory.is_dir():
        return []
    records = [_read_checkpoint(path)
               for path in sorted(directory.glob("ckpt_*.json"))]
    return sorted(records, key=lambda item: str(item.get("created_at", "")),
                  reverse=True)


__all__ = ["WORKING_DIRNAME", "MAX_CHECKPOINT_BYTES", "MAX_CHECKPOINTS",
           "RESTORED", "DIVERGENCE", "STALE_HEAD", "EXPIRED", "MISSING",
           "FIELDS", "repository_snapshot", "validate_state", "checkpoint",
           "restore", "list_checkpoints"]
