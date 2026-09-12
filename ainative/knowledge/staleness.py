"""Staleness: mark, never rewrite (convergence row 15).

A knowledge item goes stale when an explicit dependency it recorded has
changed. This module is a pure evaluator plus a decay policy table: it
reports signals (FRESH, POTENTIALLY_STALE, STALE_UNRESOLVED, UNKNOWN) and
ranking-only penalties. It NEVER rewrites canonical files, never promotes a
replacement, never deletes a candidate, never resolves a conflict and never
touches lifecycle states.

Separations kept explicit: staleness signal != candidate lifecycle state
!= representation health != trust qualification. Decay affects retrieval
ranking and review urgency only - never authority. Hard classes (security
rules, ADRs, explicit user policy) carry `decay_class: no_decay` and are
never decayed; records without an explicit class default to `weak`.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from .errors import KnowledgeError

FRESH = "FRESH"
POTENTIALLY_STALE = "POTENTIALLY_STALE"
STALE_UNRESOLVED = "STALE_UNRESOLVED"
UNKNOWN = "UNKNOWN"

DEPENDENCY_REFUSED = "KNOWLEDGE_DEPENDENCY_REFUSED"
FILE_KINDS = frozenset({"source_path", "adr_ref", "ai_context_section",
                        "canonical_section"})
DEPENDENCY_KINDS = FILE_KINDS | {"git_head", "graph_node", "module_identity"}

NO_DECAY = "no_decay"
WEAK_DECAY = "weak"
STRONGER_DECAY = "stronger"
DECAY_CLASSES = (NO_DECAY, WEAK_DECAY, STRONGER_DECAY)

_SEVERITY = {FRESH: 0, UNKNOWN: 1, POTENTIALLY_STALE: 2, STALE_UNRESOLVED: 3}
_PENALTY_BASE = {FRESH: 0.0, UNKNOWN: 0.25, POTENTIALLY_STALE: 0.5,
                 STALE_UNRESOLVED: 1.0}
_PENALTY_FACTOR = {NO_DECAY: 0.0, WEAK_DECAY: 1.0, STRONGER_DECAY: 1.5}
_REVIEW_BASE = {FRESH: 0, UNKNOWN: 1, POTENTIALLY_STALE: 2, STALE_UNRESOLVED: 3}


class _DependencyRefused(Exception):
    pass


def _within(project: Path, candidate: Path) -> bool:
    root = os.path.normcase(os.path.normpath(str(project)))
    value = os.path.normcase(os.path.normpath(str(candidate)))
    return value == root or value.startswith(root + os.sep)


def _check_file(project: Path, ref: str, digest: Any) -> tuple[str, str]:
    resolved = (project / ref).resolve()
    if not _within(project.resolve(), resolved):
        raise _DependencyRefused()
    if not resolved.is_file():
        return STALE_UNRESOLVED, "dependency file is missing"
    if not isinstance(digest, str) or not digest:
        return UNKNOWN, "no recorded digest to compare"
    try:
        current = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError:
        return UNKNOWN, "dependency file is unreadable"
    if current != digest:
        return POTENTIALLY_STALE, "dependency content changed"
    return FRESH, "recorded digest matches"


def _check_git_head(project: Path, expected: Any) -> tuple[str, str]:
    if not isinstance(expected, str) or not expected:
        return UNKNOWN, "no recorded revision"
    try:
        result = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"],
                                capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN, "git unavailable"
    if result.returncode != 0:
        return UNKNOWN, "git unavailable"
    current = result.stdout.decode("utf-8", "replace").strip()
    if current == expected:
        return FRESH, "head matches"
    return POTENTIALLY_STALE, "head moved"


def evaluate(project: Path, dependencies: Any) -> dict[str, Any]:
    """Pure evaluation. Refused refs are invisible; corrupt metadata fails closed."""

    if not isinstance(dependencies, list):
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "dependencies must be a list")
    details, refused = [], []
    signal: str | None = None
    for entry in dependencies:
        if not isinstance(entry, dict) or not isinstance(entry.get("kind"), str):
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 "dependency entries need a kind")
        kind = entry["kind"]
        ref = entry.get("ref")
        if kind not in DEPENDENCY_KINDS:
            result, reason = UNKNOWN, f"unknown dependency kind {kind!r}"
        elif kind in FILE_KINDS:
            if not isinstance(ref, str) or not ref.strip():
                raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                     "file dependency needs a ref")
            try:
                result, reason = _check_file(Path(project), ref, entry.get("digest"))
            except _DependencyRefused:
                refused.append({"kind": kind, "ref": ref,
                                "code": DEPENDENCY_REFUSED,
                                "reason": "ref is outside the project (cross-domain invisible)"})
                continue
        elif kind == "git_head":
            result, reason = _check_git_head(Path(project), ref)
        else:
            result, reason = UNKNOWN, "no resolver for this kind in v1"
        details.append({"kind": kind, "ref": ref, "signal": result, "reason": reason})
        if signal is None or _SEVERITY[result] > _SEVERITY[signal]:
            signal = result
    return {"signal": signal or UNKNOWN, "details": details, "refused": refused}


def decay_class(record: Any) -> str:
    """Explicit class wins; anything else is weak. Unknown values fail to weak."""

    value = record.get("decay_class") if isinstance(record, dict) else None
    return value if value in DECAY_CLASSES else WEAK_DECAY


def retrieval_penalty(signal: str, decay: str) -> float:
    """Ranking-only penalty. Hard classes are never decayed."""

    return round(_PENALTY_BASE.get(signal, 0.25)
                 * _PENALTY_FACTOR.get(decay, 1.0), 3)


def review_priority(signal: str, decay: str) -> int:
    """Review urgency tier 0-3. Decay can raise urgency, never authority."""

    base = _REVIEW_BASE.get(signal, 1)
    if decay == STRONGER_DECAY and base in (2, 3):
        base = min(3, base + 1)
    return base


__all__ = ["FRESH", "POTENTIALLY_STALE", "STALE_UNRESOLVED", "UNKNOWN",
           "DEPENDENCY_REFUSED", "FILE_KINDS", "DEPENDENCY_KINDS",
           "NO_DECAY", "WEAK_DECAY", "STRONGER_DECAY", "DECAY_CLASSES",
           "evaluate", "decay_class", "retrieval_penalty", "review_priority"]
