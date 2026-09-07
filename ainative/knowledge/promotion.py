"""Safe promotion: one audited patch against a known base digest.

Pipeline per candidate: resolve exactly one target, load its current
bytes, generate the minimal patch, validate the expected base digest,
write via temp plus atomic replace, re-read to confirm, then move the
candidate to PROMOTED with an audit event carrying both digests. Any
base mismatch aborts with STALE_BASE before a byte is written; a crash
between the file write and the audit is healed by `reconcile`.
Human approval policy lives one layer up (K4b CLI); this engine never
decides WHO may promote, only that the mechanics are safe.
"""

from __future__ import annotations

import difflib
from hashlib import sha256
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from . import store as storelib
from . import targets as targetslib
from .errors import KnowledgeError
from .provenance import now

ADD = "ADD"
MERGE = "MERGE"
REFINE = "REFINE"
SUPERSEDE = "SUPERSEDE"

WRITES = frozenset({ADD, MERGE, REFINE, SUPERSEDE})

MAX_DIFF_PREVIEW_LINES = 100


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _relative(project: Path, dest: Path) -> str:
    try:
        return dest.resolve().relative_to(Path(project).resolve()).as_posix()
    except ValueError:
        return dest.name


def _match_newlines(current: bytes, text: str) -> bytes:
    """Keep the file's newline style so the diff stays minimal."""

    if b"\r\n" in current:
        return text.replace("\n", "\r\n").encode("utf-8")
    return text.encode("utf-8")


def render_block(candidate: dict, *, operation: str, actor: str) -> str:
    """One attributed Markdown section. Deterministic, no prose invented."""

    evidence = candidate.get("evidence", [])
    refs = ", ".join(f"{item.get('type')} {item.get('locator', '-')}"
                     for item in evidence) or "none yet"
    provenance = candidate.get("provenance", {})
    return (
        f"### {candidate['claim']}\n"
        f"- Source: knowledge {candidate['candidate_id']} "
        f"({candidate['kind']}), {provenance.get('agent', '?')}, "
        f"{provenance.get('timestamp', '?')}\n"
        f"- Operation: {operation} by {actor}\n"
        f"- Evidence: {refs}\n"
    )


def render_adr(candidate: dict, *, number: int, actor: str) -> str:
    """A new ADR file following the repo's Context/Decision layout."""

    provenance = candidate.get("provenance", {})
    return (
        f"# ADR-{number:04d} — {candidate['claim'][:80]}\n"
        "\n"
        "- Status: proposed\n"
        f"- Date: {now()[:10]}\n"
        f"- Promoted from: {candidate['candidate_id']} by {actor}\n"
        "\n"
        "## Context\n"
        "\n"
        f"{candidate['claim']}\n"
        "\n"
        "## Decision\n"
        "\n"
        f"{candidate['claim']}\n"
        "\n"
        "## Provenance\n"
        "\n"
        f"Agent: {provenance.get('agent', '?')}, "
        f"session: {provenance.get('session', '?')}, "
        f"head: {provenance.get('git_head', '?')}\n"
    )


def _locate(text: str, anchor_text: str | None, operation: str) -> int:
    """The single occurrence an edit needs, or a refusal. Pure function."""

    if operation == ADD:
        return -1
    if not anchor_text:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"{operation} needs an explicit --anchor-text")
    count = text.count(anchor_text)
    if count == 0:
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             "anchor text not found in target")
    if count > 1:
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             f"anchor text occurs {count} times; narrow it")
    return text.index(anchor_text)


def _build(current: bytes, candidate: dict, *, operation: str, actor: str,
           anchor_text: str | None, dest: Path, project: Path) -> str:
    text = current.decode("utf-8", errors="replace")
    if not current:
        if dest.parent.name != "adr":
            raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                                 "refusing to create a non-ADR canonical file")
        number = targetslib.next_adr_number(project)
        return render_adr(candidate, number=number, actor=actor)
    position = _locate(text, anchor_text, operation)
    block = render_block(candidate, operation=operation, actor=actor)
    if operation == ADD:
        separator = "" if text.endswith("\n") else "\n"
        return text + separator + "\n" + block
    if operation == MERGE:
        line_end = text.index("\n", position) + 1 if "\n" in text[position:] else len(text)
        return text[:line_end] + block + text[line_end:]
    if operation == REFINE:
        return text[:position] + candidate["claim"] + text[position + len(anchor_text):]
    line_start = text.rfind("\n", 0, position) + 1
    note = (f"> Superseded by knowledge {candidate['candidate_id']} "
            f"(see new section below).\n")
    separator = "" if text.endswith("\n") else "\n"
    return text[:line_start] + note + text[line_start:] + separator + "\n" + block


def _preview(current: bytes, new_text: str) -> list[str]:
    diff = list(difflib.unified_diff(
        current.decode("utf-8", errors="replace").splitlines(),
        new_text.splitlines(), lineterm=""))
    if len(diff) > MAX_DIFF_PREVIEW_LINES:
        diff = diff[:MAX_DIFF_PREVIEW_LINES] + [f"... ({len(diff)} more lines)"]
    return diff


def plan_promotion(project: Path, candidate_id: str, *, operation: str,
                   actor: str, target: str | None = None,
                   anchor_text: str | None = None) -> dict[str, Any]:
    """Compute the patch. Reads only; the returned plan applies it."""

    if operation not in WRITES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown promotion operation {operation!r}")
    candidate = storelib.inspect_candidate(project, candidate_id)
    if candidate["status"] != "READY_FOR_PROMOTION":
        raise KnowledgeError("KNOWLEDGE_BAD_TRANSITION",
                             f"promote needs READY_FOR_PROMOTION, "
                             f"found {candidate['status']}",
                             current=candidate["status"])
    dest = targetslib.resolve(project, candidate, target=target)
    current = dest.read_bytes() if dest.is_file() else b""
    new_text = _build(current, candidate, operation=operation, actor=actor,
                      anchor_text=anchor_text, dest=dest, project=Path(project))
    return {"candidate_id": candidate_id, "operation": operation,
            "target": _relative(Path(project), dest),
            "base_digest": _digest(current),
            "result_digest": _digest(_match_newlines(current, new_text)),
            "actor": actor, "anchor_text": anchor_text,
            "diff_preview": _preview(current, new_text),
            "new_text": new_text}


def apply_promotion(project: Path, candidate_id: str, *, operation: str,
                    actor: str, target: str | None = None,
                    anchor_text: str | None = None,
                    expect_base: str | None = None) -> dict[str, Any]:
    """Apply one planned patch: base-checked, atomic, audited."""

    plan = plan_promotion(project, candidate_id, operation=operation, actor=actor,
                          target=target, anchor_text=anchor_text)
    if expect_base is not None and plan["base_digest"] != expect_base:
        raise KnowledgeError("KNOWLEDGE_STALE_BASE",
                             "target changed since the preview; re-plan",
                             expected=expect_base, actual=plan["base_digest"])
    dest = Path(project) / plan["target"]
    current = dest.read_bytes() if dest.is_file() else b""
    if _digest(current) != plan["base_digest"]:
        raise KnowledgeError("KNOWLEDGE_PROMOTION_CONFLICT",
                             "target changed under this promotion; re-plan")
    payload = _match_newlines(current, plan["new_text"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    statelib.write_bytes_atomic(dest, payload)
    if _digest(dest.read_bytes()) != plan["result_digest"]:
        raise KnowledgeError("KNOWLEDGE_STORE_CORRUPTED",
                             "promoted bytes do not match the plan; aborting")
    storelib.set_status(Path(project), candidate_id, "PROMOTED", actor=actor)
    storelib.record_audit(Path(project), candidate_id=candidate_id,
                          operation="PROMOTE",
                          detail={"promote_operation": operation,
                                  "target": plan["target"],
                                  "base_digest": plan["base_digest"],
                                  "result_digest": plan["result_digest"]},
                          actor=actor)
    return {"candidate_id": candidate_id, "operation": operation,
            "target": plan["target"], "base_digest": plan["base_digest"],
            "result_digest": plan["result_digest"],
            "diff_preview": plan["diff_preview"]}


def reconcile(project: Path, candidate_id: str) -> dict[str, Any]:
    """Heal a crash between the file write and the audit. Never rewrites files."""

    candidate = storelib.inspect_candidate(project, candidate_id)
    promotes = [event for event in storelib.read_audit(Path(project))
                if event.get("candidate_id") == candidate_id
                and event.get("operation") == "PROMOTE"]
    if candidate["status"] == "PROMOTED" and promotes:
        return {"candidate_id": candidate_id, "state": "consistent"}
    if candidate["status"] == "PROMOTED" and not promotes:
        storelib.record_audit(Path(project), candidate_id=candidate_id,
                              operation="RECONCILE",
                              detail={"note": "PROMOTED without a PROMOTE event; "
                                              "no file was touched, human review"},
                              actor="reconcile")
        return {"candidate_id": candidate_id, "state": "healed-audit"}
    if promotes and candidate["status"] == "READY_FOR_PROMOTION":
        last = promotes[-1]
        dest = Path(project) / str(last["detail"].get("target", ""))
        current = _digest(dest.read_bytes()) if dest.is_file() else None
        if current == last["detail"].get("result_digest"):
            storelib.set_status(Path(project), candidate_id, "PROMOTED",
                                actor="reconcile")
            storelib.record_audit(Path(project), candidate_id=candidate_id,
                                  operation="RECONCILE",
                                  detail={"note": "status healed after a crash "
                                                  "between write and audit"},
                                  actor="reconcile")
            return {"candidate_id": candidate_id, "state": "healed-status"}
        return {"candidate_id": candidate_id, "state": "diverged",
                "detail": "target no longer holds the promoted bytes; human review"}
    return {"candidate_id": candidate_id, "state": "nothing-to-heal"}


__all__ = ["ADD", "MERGE", "REFINE", "SUPERSEDE", "WRITES",
           "MAX_DIFF_PREVIEW_LINES", "render_block", "render_adr",
           "plan_promotion", "apply_promotion", "reconcile"]