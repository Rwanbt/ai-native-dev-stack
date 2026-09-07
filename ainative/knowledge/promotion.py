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
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from . import store as storelib
from . import targets as targetslib
from . import trust as trustlib
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


def _heading(candidate: dict) -> str:
    """Section heading: the claim first line, so multiline claims stay put."""

    return "### " + candidate["claim"].splitlines()[0][:120]


def render_block(candidate: dict, *, operation: str, actor: str) -> str:
    """One attributed Markdown section. Deterministic, no prose invented."""

    evidence = candidate.get("evidence", [])
    refs = ", ".join(f"{item.get('type')} {item.get('locator', '-')}"
                     for item in evidence) or "none yet"
    provenance = candidate.get("provenance", {})
    return (
        f"{_heading(candidate)}\n"
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


def _git(project: Path, *args: str, timeout: int = 10):
    try:
        return subprocess.run(["git", "-C", str(project), *args],
                              capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _git_head(project: Path) -> str | None:
    result = _git(project, "rev-parse", "HEAD")
    if result is None or result.returncode != 0:
        return None
    head = result.stdout.strip()
    return head or None


def _section_span(new_text: str, *, operation: str, claim: str,
                  anchor_text: str | None, is_new: bool) -> tuple[str | None, str]:
    """Controlled-section locator plus its text. Pure function.

    ADD/MERGE/SUPERSEDE sections open with the claim heading and run to
    the next same-or-higher heading or EOF. REFINE spans the inserted
    claim. New files span everything. A missing heading degrades to a
    whole-file span (marker None) rather than a fabricated locator.
    """

    new_text = new_text.replace("\r\n", "\n")
    if is_new:
        lines = new_text.splitlines()
        return (lines[0] if lines else None), new_text
    if operation == "REFINE" and anchor_text:
        return anchor_text, claim
    heading = "### " + claim.splitlines()[0][:120]
    lines = new_text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines)
                  if line.rstrip("\n") == heading), None)
    if start is None:
        return None, new_text
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("#")
                and lines[index][1:2] in ("", " ", "#")), len(lines))
    return heading, "".join(lines[start:end])


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
    locator, span = _section_span(new_text, operation=operation,
                                  claim=candidate["claim"],
                                  anchor_text=anchor_text,
                                  is_new=not current)
    section = {"locator": locator,
               "digest": _digest(span.encode("utf-8"))}
    return {"candidate_id": candidate_id, "operation": operation,
            "target": _relative(Path(project), dest),
            "base_digest": _digest(current),
            "result_digest": _digest(_match_newlines(current, new_text)),
            "actor": actor, "anchor_text": anchor_text,
            "diff_preview": _preview(current, new_text),
            "section": section,
            "new_text": new_text}


def apply_promotion(project: Path, candidate_id: str, *, operation: str,
                    actor: str, target: str | None = None,
                    anchor_text: str | None = None,
                    expect_base: str | None = None,
                    approval: dict[str, Any] | None = None,
                    verify=None) -> dict[str, Any]:
    """Apply one planned patch: base-checked, atomic, receipted, audited.

    `approval` carries the trust inputs (mode, capability_status,
    evidence_status, authority_ref, attestation_ref); omitted means a
    ceremony receipt, always UNVERIFIED (S3/S7). `verify` is the
    injected authority callback owning the Work Plane primitive (S19);
    VERIFIED claims without one fail closed (S15).
    """

    plan = plan_promotion(project, candidate_id, operation=operation, actor=actor,
                          target=target, anchor_text=anchor_text)
    candidate = storelib.inspect_candidate(Path(project), candidate_id)
    request = approval or {}
    receipt = trustlib.build_receipt(
        mode=request.get("mode", trustlib.TRUSTED_OPERATOR_CEREMONY),
        capability_status=request.get("capability_status", "UNKNOWN"),
        evidence_status=request.get("evidence_status", trustlib.UNVERIFIED_CEREMONY),
        approval_digest_value=trustlib.approval_digest(
            decision_id=candidate_id, target=plan["target"], operation=operation,
            scope=candidate.get("scope", {}), base_digest=plan["base_digest"],
            intended_result_digest=plan["result_digest"]),
        authority_ref=request.get("authority_ref"),
        attestation_ref=request.get("attestation_ref"))
    qualification = trustlib.validate_receipt(receipt, verify=verify)
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
                                  "result_digest": plan["result_digest"],
                                  "section": plan["section"],
                                  "promotion_commit": _git_head(Path(project)),
                                  "approval": receipt,
                                  "trust_qualification": qualification},
                          actor=actor)
    return {"candidate_id": candidate_id, "operation": operation,
            "target": plan["target"], "base_digest": plan["base_digest"],
            "result_digest": plan["result_digest"],
            "diff_preview": plan["diff_preview"],
            "approval": receipt, "trust_qualification": qualification}


def describe_reconcile(project: Path, candidate_id: str) -> dict[str, Any]:
    """Decide what a crash left behind. Reads only, never writes."""

    candidate = storelib.inspect_candidate(project, candidate_id)
    promotes = [event for event in storelib.read_audit(Path(project))
                if event.get("candidate_id") == candidate_id
                and event.get("operation") == "PROMOTE"]
    if candidate["status"] == "PROMOTED" and promotes:
        return {"candidate_id": candidate_id, "state": "consistent"}
    if candidate["status"] == "PROMOTED" and not promotes:
        return {"candidate_id": candidate_id, "state": "needs-audit-heal"}
    if promotes and candidate["status"] == "READY_FOR_PROMOTION":
        last = promotes[-1]
        dest = Path(project) / str(last["detail"].get("target", ""))
        current = _digest(dest.read_bytes()) if dest.is_file() else None
        if current == last["detail"].get("result_digest"):
            return {"candidate_id": candidate_id, "state": "needs-status-heal"}
        return {"candidate_id": candidate_id, "state": "diverged",
                "detail": "target no longer holds the promoted bytes; human review"}
    return {"candidate_id": candidate_id, "state": "nothing-to-heal"}


def reconcile(project: Path, candidate_id: str) -> dict[str, Any]:
    """Heal a crash between the file write and the audit. Never rewrites files."""

    decision = describe_reconcile(project, candidate_id)
    if decision["state"] == "needs-audit-heal":
        storelib.record_audit(Path(project), candidate_id=candidate_id,
                              operation="RECONCILE",
                              detail={"note": "PROMOTED without a PROMOTE event; "
                                              "no file was touched, human review"},
                              actor="reconcile")
        return {"candidate_id": candidate_id, "state": "healed-audit"}
    if decision["state"] == "needs-status-heal":
        storelib.set_status(Path(project), candidate_id, "PROMOTED",
                            actor="reconcile")
        storelib.record_audit(Path(project), candidate_id=candidate_id,
                              operation="RECONCILE",
                              detail={"note": "status healed after a crash "
                                              "between write and audit"},
                              actor="reconcile")
        return {"candidate_id": candidate_id, "state": "healed-status"}
    return decision


_REVERT_PATTERN = None


def _revert_pattern():
    global _REVERT_PATTERN
    if _REVERT_PATTERN is None:
        import re as _re
        _REVERT_PATTERN = _re.compile(r"\brevert\b|\bback\s?out\b", _re.IGNORECASE)
    return _REVERT_PATTERN


def _heading_end(lines: list[str], start: int) -> int:
    return next((index for index in range(start + 1, len(lines))
                 if lines[index].startswith("#")
                 and lines[index][1:2] in ("", " ", "#")), len(lines))


def _locate_spans(text: str, locator: str | None) -> list[str]:
    """Controlled-section spans for a locator. Literal matching only."""

    if not locator:
        return []
    lines = text.splitlines(keepends=True)
    if locator.startswith("#"):
        spans = []
        for index, line in enumerate(lines):
            if line.rstrip("\n") == locator:
                spans.append("".join(lines[index:_heading_end(lines, index)]))
        return spans
    spans = []
    cursor = 0
    while True:
        found = text.find(locator, cursor)
        if found < 0:
            return spans
        spans.append(text[found:found + len(locator)])
        cursor = found + len(locator)


def _target_commits(project: Path, rel_target: str,
                    promotion_commit: str | None) -> list[tuple[str, str]] | None:
    """(sha, subject) touching target after the promotion commit. None if git mute."""

    args = ["log", "--max-count=50", "--format=%H %s"]
    if promotion_commit:
        args.append(f"{promotion_commit}..HEAD")
    args += ["--", rel_target]
    result = _git(Path(project), *args)
    if result is None or result.returncode != 0:
        return None
    commits = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition(" ")
        if sha.strip():
            commits.append((sha.strip(), subject.strip()))
    return commits


def _section_health(project: Path, dest: Path, section: dict | None,
                    promotion_commit: str | None) -> tuple[str, str]:
    """Representation health of one promoted span (V3.3.1 S28). Read-only."""

    try:
        raw = dest.read_bytes()
    except OSError:
        return trustlib.MISSING, "target unreadable"
    locator = (section or {}).get("locator")
    expected = (section or {}).get("digest")
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if locator is None:
        if expected is not None and _digest(text.encode("utf-8")) == expected:
            return trustlib.HEALTHY, "whole-file span matches"
        return _history_verdict(Path(project), dest, promotion_commit)
    spans = _locate_spans(text, locator)
    if len(spans) == 1:
        if _digest(spans[0].encode("utf-8")) == expected:
            return trustlib.HEALTHY, "promoted section matches result digest"
        return trustlib.SUPERSEDED, "section present but altered"
    if len(spans) > 1:
        return trustlib.AMBIGUOUS, "several incompatible spans match"
    return _history_verdict(Path(project), dest, promotion_commit)


def _history_verdict(project: Path, dest: Path,
                     promotion_commit: str | None) -> tuple[str, str]:
    try:
        rel = dest.resolve().relative_to(Path(project).resolve()).as_posix()
    except ValueError:
        return trustlib.MISSING, "target outside project"
    commits = _target_commits(Path(project), rel, promotion_commit)
    if commits is None:
        return trustlib.MISSING, "no git history to establish continuity"
    if not commits:
        return trustlib.MISSING, "span absent, no later target history"
    if any(_revert_pattern().search(subject) for _, subject in commits):
        return trustlib.REVERTED, "span removed by a revert-like commit"
    return trustlib.SUPERSEDED, "span absent after later target change"


def describe_full(project: Path, candidate_id: str, *,
                  verify=None) -> dict[str, Any]:
    """Lifecycle state, representation health, trust qualification. Read-only."""

    candidate = storelib.inspect_candidate(Path(project), candidate_id)
    promotes = [event for event in storelib.read_audit(Path(project))
                if event.get("candidate_id") == candidate_id
                and event.get("operation") == "PROMOTE"]
    if not promotes:
        return {"candidate_id": candidate_id,
                "lifecycle_state": candidate["status"],
                "representation_health": trustlib.MISSING,
                "trust_qualification": trustlib.QUALIFIED_UNVERIFIED,
                "receipt": None, "target": None,
                "note": "never promoted"}
    detail = promotes[-1].get("detail", {})
    dest = Path(project) / str(detail.get("target", ""))
    health, health_detail = _section_health(Path(project), dest,
                                            detail.get("section"),
                                            detail.get("promotion_commit"))
    receipt = detail.get("approval")
    if receipt is None:
        receipt = {"mode": trustlib.TRUSTED_OPERATOR_CEREMONY,
                   "capability_status": "UNKNOWN",
                   "evidence_status": trustlib.UNVERIFIED_CEREMONY,
                   "approval_digest": "legacy-unbound",
                   "authority_ref": None, "attestation_ref": None}
    qualification = trustlib.derive_qualification(receipt, verify=verify)
    return {"candidate_id": candidate_id,
            "lifecycle_state": candidate["status"],
            "representation_health": health,
            "representation_detail": health_detail,
            "trust_qualification": qualification,
            "receipt": receipt, "target": detail.get("target")}


__all__ = ["ADD", "MERGE", "REFINE", "SUPERSEDE", "WRITES",
           "MAX_DIFF_PREVIEW_LINES", "render_block", "render_adr",
           "plan_promotion", "apply_promotion", "describe_reconcile", "reconcile",
           "describe_full"]