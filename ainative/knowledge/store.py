"""Locked, bounded, crash-safe candidate/control persistence (B1, PR3).

Layout (B1 S2):

```text
.ai-native/state/knowledge/candidates.jsonl   enveloped candidates (raw claim)
.ai-native/state/knowledge/supports.jsonl     enveloped support + evidence
.ai-native/audit/knowledge/audit.jsonl        enveloped audit + tombstones
```

Every mutation: policy check, containment check, then the shared
lifecycle `project_guard` (inter-process) around reload, validate,
bounds-check and atomic replace. Readers validate every line and fail
closed with file plus line number; unknown schemas fail closed in the
envelope. Writer temp files (`.tmp-*`) never match `*.jsonl`, so a
crashed writer leaves at most an ignored temp file — never a torn
record. No second transaction engine: atomic replace plus the shared
guard is the whole crash story, and the concurrency test proves it
with real processes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ainative.lifecycle import paths as pathslib
from ainative.lifecycle import state as statelib
from ainative.lifecycle.lock import project_guard

from . import paths as controlpaths
from . import states as stateslib
from .assertions import tombstone as make_tombstone
from .bounds import Bounds
from .envelope import unwrap, wrap
from .errors import KnowledgeError
from .identity import screen_secret

CANDIDATES_FILE = "candidates.jsonl"
SUPPORTS_FILE = "supports.jsonl"
AUDIT_FILE = "audit.jsonl"

now = statelib.now

CANDIDATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
KEBAB = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")
MAX_TEXT = 4000
MAX_DETAIL_STRING = 1000


def _bounded(name: str, value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"{name} must be nonempty text")
    if len(value) > limit:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"{name} exceeds {limit} chars")
    return value


def _kebab(name: str, value: Any) -> str:
    _bounded(name, value, 64)
    if not KEBAB.match(value):
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"{name} must be lowercase kebab")
    return value


def _require_dict(name: str, value: Any) -> dict:
    if not isinstance(value, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"{name} must be an object")
    return value


def _scan(name: str, *texts: Any) -> None:
    for text in texts:
        if isinstance(text, str) and screen_secret(text) is not None:
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 f"{name} fails secret screening")


def _locator(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "locator must be short text")
    if "://" in value:
        if value.startswith(("http://", "https://")):
            return value
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "locator scheme refused")
    try:
        pathslib.validate_relative(value)
    except Exception as error:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"locator refused: {error}") from error
    return value


def validate_candidate(raw: Any, *, bounds: Bounds) -> dict:
    """Structural validation (B1 S4). Identity depth is caller-side."""

    if not isinstance(raw, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "candidate is not an object")
    if raw.get("schema_version") != 1:
        raise KnowledgeError("KNOWLEDGE_SCHEMA_UNKNOWN",
                             "candidate schema_version unsupported")
    identifier = raw.get("candidate_id", "")
    if not isinstance(identifier, str) or not CANDIDATE_ID.match(identifier):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "illegal candidate_id")
    _kebab("kind", raw.get("kind"))
    state = raw.get("state", "")
    if state not in stateslib.STATES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"unknown state {state!r}")
    for name in ("created_at", "updated_at"):
        _bounded(name, raw.get(name), 64)
    _require_dict("source", raw.get("source"))
    _require_dict("scope", raw.get("scope"))
    claim = _bounded("claim", raw.get("claim"), MAX_TEXT)
    identity = _require_dict("identity", raw.get("identity"))
    _bounded("identity_key", identity.get("identity_key"), 253)
    if not isinstance(identity.get("identity_key_grammar_version"), int):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "identity grammar version int")
    _bounded("assertion_hash", raw.get("assertion_hash"), 128)
    if not isinstance(raw.get("assertion_normalization_version"), int):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "assertion version int")
    _bounded("hash_algorithm", raw.get("hash_algorithm"), 64)
    _require_dict("provenance", raw.get("provenance"))
    _scan("claim", claim)
    payload = json.dumps(raw, sort_keys=True)
    if len(payload.encode("utf-8")) > bounds.max_candidate_payload:
        raise KnowledgeError("KNOWLEDGE_CANDIDATE_TOO_LARGE",
                             f"candidate exceeds {bounds.max_candidate_payload} bytes")
    return raw


def validate_support(raw: Any, *, bounds: Bounds) -> dict:
    if not isinstance(raw, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "support is not an object")
    _bounded("support_id", raw.get("support_id"), 128)
    _bounded("candidate_id", raw.get("candidate_id"), 128)
    _kebab("kind", raw.get("kind"))
    locator = _locator(raw.get("locator", ""))
    _scan("support", locator, raw.get("digest", ""), raw.get("note", ""))
    payload = json.dumps(raw, sort_keys=True)
    if len(payload.encode("utf-8")) > bounds.max_support_payload:
        raise KnowledgeError("KNOWLEDGE_CANDIDATE_TOO_LARGE",
                             f"support exceeds {bounds.max_support_payload} bytes")
    return raw


def validate_audit_detail(detail: Any) -> dict:
    if not isinstance(detail, dict):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "audit detail must be an object")
    for key, value in detail.items():
        if not isinstance(key, str):
            raise KnowledgeError("KNOWLEDGE_MALFORMED", "audit detail keys str")
        if isinstance(value, str):
            if len(value) > MAX_DETAIL_STRING:
                raise KnowledgeError("KNOWLEDGE_MALFORMED", "audit detail str too long")
            _scan("audit detail", value)
        elif not isinstance(value, (int, float, bool)) and value is not None:
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 "audit detail holds scalars only")
    return detail


def _paths(project: Path) -> dict[str, Path]:
    root = Path(project)
    return {"candidates": controlpaths.state_dir(root) / CANDIDATES_FILE,
            "supports": controlpaths.state_dir(root) / SUPPORTS_FILE,
            "audit": controlpaths.audit_dir(root) / AUDIT_FILE}


def _read_envelopes(path: Path) -> list[dict]:
    """Every enveloped line, any record type. Temp files never match."""

    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             f"cannot read {path.name}: {error}") from error
    envelopes = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            envelope = unwrap(json.loads(line))
        except KnowledgeError as error:
            raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                                 f"{path.name} line {number}: {error}") from error
        except ValueError as error:
            raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                                 f"{path.name} line {number} is not JSON") from error
        envelopes.append(envelope)
    return envelopes


def _read_lines(path: Path, kind: str) -> list[dict]:
    return [envelope["payload"] for envelope in _read_envelopes(path)
            if envelope["record_type"] == kind]


def _rewrite(path: Path, kind: str, records: list[dict]) -> None:
    payload = "".join(json.dumps(wrap(kind, _record_id(item, kind),
                                      item), sort_keys=True) + "\n"
                      for item in records)
    statelib.write_atomic(path, payload)


def _record_id(item: dict, kind: str) -> str:
    for key in ("candidate_id", "support_id", "event_id", "assertion_hash"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return f"{kind}-noid"


def _counts(project: Path) -> dict[str, int]:
    paths = _paths(project)
    support_types = [envelope["record_type"]
                     for envelope in _read_envelopes(paths["supports"])]
    audit_types = [envelope["record_type"]
                   for envelope in _read_envelopes(paths["audit"])]
    return {"candidates": len(_read_lines(paths["candidates"], "candidate")),
            "supports": support_types.count("support"),
            "tombstones": support_types.count("tombstone"),
            "audit": audit_types.count("audit")}


def _total_bytes(project: Path) -> int:
    total = 0
    for path in _paths(project).values():
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _guarded(project: Path, fn):
    root = Path(project)
    controlpaths.require_policy(root)
    controlpaths.ensure_contained(root)
    with project_guard(root):
        return fn()


def append_candidate(project: Path, record: dict, *,
                     bounds: Bounds | None = None) -> dict:
    """Validate, bound-check and durably append one candidate."""

    limits = bounds or Bounds()

    def _run() -> dict:
        stored = validate_candidate(record, bounds=limits)
        paths = _paths(Path(project))
        existing = _read_lines(paths["candidates"], "candidate")
        if any(item.get("candidate_id") == stored["candidate_id"] for item in existing):
            raise KnowledgeError("KNOWLEDGE_MALFORMED", "duplicate candidate_id")
        if len(existing) >= limits.max_candidate_count:
            raise KnowledgeError("KNOWLEDGE_STORE_FULL", "candidate store full")
        if _total_bytes(Path(project)) > limits.max_total_bytes:
            raise KnowledgeError("KNOWLEDGE_STORE_FULL", "control storage full")
        existing.append(stored)
        _rewrite(paths["candidates"], "candidate", existing)
        return stored

    return _guarded(project, _run)


def append_support(project: Path, record: dict, *,
                   bounds: Bounds | None = None) -> dict:
    limits = bounds or Bounds()

    def _run() -> dict:
        stored = validate_support(record, bounds=limits)
        paths = _paths(Path(project))
        envelopes = _read_envelopes(paths["supports"])
        supports = [envelope["payload"] for envelope in envelopes
                    if envelope["record_type"] == "support"]
        if any(item.get("support_id") == stored["support_id"] for item in supports):
            raise KnowledgeError("KNOWLEDGE_MALFORMED", "duplicate support_id")
        if _total_bytes(Path(project)) > limits.max_total_bytes:
            raise KnowledgeError("KNOWLEDGE_STORE_FULL", "control storage full")
        supports.append(stored)
        tombstones = [envelope["payload"] for envelope in envelopes
                      if envelope["record_type"] == "tombstone"]
        _rewrite_supports(paths["supports"], supports, tombstones)
        return stored

    return _guarded(project, _run)


def _rewrite_supports(path: Path, supports: list[dict], tombstones: list[dict]) -> None:
    payload = "".join(json.dumps(wrap("support", item["support_id"], item),
                                 sort_keys=True) + "\n" for item in supports)
    payload += "".join(json.dumps(wrap("tombstone", item["assertion_hash"], item),
                                  sort_keys=True) + "\n" for item in tombstones)
    statelib.write_atomic(path, payload)


def append_tombstone(project: Path, assertion_hash_value: str, *, reason: str,
                     actor: str, bounds: Bounds | None = None) -> dict:
    limits = bounds or Bounds()

    def _run() -> dict:
        marker = make_tombstone(assertion_hash_value, reason=reason, actor=actor)
        paths = _paths(Path(project))
        envelopes = _read_envelopes(paths["audit"])
        tombstones = [envelope["payload"] for envelope in envelopes
                      if envelope["record_type"] == "tombstone"]
        if any(item.get("assertion_hash") == marker["assertion_hash"]
               for item in tombstones):
            return marker
        events = [envelope["payload"] for envelope in envelopes
                  if envelope["record_type"] == "audit"]
        if len(events) >= limits.max_audit_count:
            raise KnowledgeError("KNOWLEDGE_STORE_FULL", "audit store full")
        tombstones.append(marker)
        payload = "".join(json.dumps(wrap("audit", item.get("event_id", "audit"),
                                          item), sort_keys=True) + "\n"
                          for item in events)
        payload += "".join(json.dumps(wrap("tombstone", item["assertion_hash"], item),
                                      sort_keys=True) + "\n" for item in tombstones)
        statelib.write_atomic(paths["audit"], payload)
        return marker

    return _guarded(project, _run)


def record_audit(project: Path, *, operation: str, actor: str,
                 candidate_id: str | None = None,
                 detail: dict | None = None,
                 bounds: Bounds | None = None) -> dict:
    limits = bounds or Bounds()

    def _run() -> dict:
        _kebab("operation", operation)
        _bounded("actor", actor, 128)
        event = {"event_id": statelib.new_identifier("evt"),
                 "candidate_id": candidate_id, "operation": operation,
                 "detail": validate_audit_detail(detail or {}),
                 "actor": actor, "timestamp": now()}
        paths = _paths(Path(project))
        envelopes = _read_envelopes(paths["audit"])
        events = [envelope["payload"] for envelope in envelopes
                  if envelope["record_type"] == "audit"]
        if len(events) >= limits.max_audit_count:
            raise KnowledgeError("KNOWLEDGE_STORE_FULL", "audit store full")
        tombstones = [envelope["payload"] for envelope in envelopes
                      if envelope["record_type"] == "tombstone"]
        events.append(event)
        payload = "".join(json.dumps(wrap("audit", item["event_id"], item),
                                     sort_keys=True) + "\n" for item in events)
        payload += "".join(json.dumps(wrap("tombstone", item["assertion_hash"], item),
                                      sort_keys=True) + "\n" for item in tombstones)
        statelib.write_atomic(paths["audit"], payload)
        return event

    return _guarded(project, _run)


def list_candidates(project: Path) -> list[dict]:
    controlpaths.ensure_contained(Path(project))
    return _read_lines(_paths(Path(project))["candidates"], "candidate")


def get_candidate(project: Path, candidate_id: str) -> dict:
    for item in list_candidates(project):
        if item.get("candidate_id") == candidate_id:
            return item
    raise KnowledgeError("KNOWLEDGE_NOT_FOUND", f"unknown candidate {candidate_id!r}")


def list_supports(project: Path, candidate_id: str) -> list[dict]:
    controlpaths.ensure_contained(Path(project))
    return [item for item in _read_lines(
        _paths(Path(project))["supports"], "support")
        if item.get("candidate_id") == candidate_id]


def list_audit(project: Path) -> list[dict]:
    controlpaths.ensure_contained(Path(project))
    paths = _paths(Path(project))
    return ([item for item in _read_lines(paths["audit"], "audit")]
            + [item for item in _read_lines(paths["audit"], "tombstone")])


def storage_status(project: Path, *, bounds: Bounds | None = None) -> dict:
    """Counts, bytes and bound warnings. Read-only."""

    limits = bounds or Bounds()
    counts = _counts(Path(project))
    total = _total_bytes(Path(project))
    warnings = []
    if counts["candidates"] >= limits.max_candidate_count * limits.warning_threshold:
        warnings.append("candidate count near bound")
    if counts["audit"] >= limits.max_audit_count * limits.warning_threshold:
        warnings.append("audit count near bound")
    if total >= limits.max_total_bytes * limits.warning_threshold:
        warnings.append("control storage near bound")
    return {"counts": counts, "total_bytes": total, "warnings": warnings,
            "bounds": {"max_candidate_count": limits.max_candidate_count,
                       "max_audit_count": limits.max_audit_count,
                       "max_total_bytes": limits.max_total_bytes}}


__all__ = ["CANDIDATES_FILE", "SUPPORTS_FILE", "AUDIT_FILE",
           "validate_candidate", "validate_support", "validate_audit_detail",
           "append_candidate", "append_support", "append_tombstone",
           "record_audit", "list_candidates", "get_candidate",
           "list_supports", "list_audit", "storage_status"]
