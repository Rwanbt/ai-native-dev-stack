"""Retrieval: deterministic-first context bundles under hard budgets.

Order is architecture (plan Phase K5): deterministic context first
(AGENTS.md, nearest AI_CONTEXT.md, AI_SUMMARY.md, named ADRs), then
promotable candidates as explicitly UNVERIFIED notes, then (K5b)
structural and semantic tiers. Every excerpt carries a trust label
(SYSTEM RULE is never emitted by this module — the harness owns it;
see KNOWLEDGE-SECURITY.md section 1), canonical status always
outweighs similarity, and budgets truncate by rank — never by dumping
everything. Semantic recall runs only on explicit `--recall` intent,
never on every call (Active Recall).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ainative.lifecycle.errors import LifecycleError
from ainative.lifecycle.paths import resolve_within

from . import store as storelib
from .candidate import TERMINAL, validate_locator
from .errors import KnowledgeError
from .provenance import now

CANONICAL = "CANONICAL PROJECT KNOWLEDGE"
UNVERIFIED = "UNVERIFIED CANDIDATE"
EXTERNAL = "EXTERNAL CONTENT"

WEIGHTS = {"AGENTS.md": 100, "AI_CONTEXT.md": 80, "ADR": 70,
           "AI_SUMMARY.md": 60, "candidate": 20}
SCOPE_BONUS = 30


@dataclass
class Budgets:
    """Hard context budgets. Exceeded means rank harder, never dump all."""

    max_items: int = 20
    max_bytes: int = 65536
    max_excerpt_chars: int = 2000
    max_candidates: int = 5


@dataclass
class BundleItem:
    label: str
    kind: str
    locator: str
    excerpt: str
    score: int = 0
    truncated: bool = False

    def to_record(self) -> dict[str, Any]:
        return {"label": self.label, "kind": self.kind, "locator": self.locator,
                "excerpt": self.excerpt, "score": self.score,
                "truncated": self.truncated}


def estimate_tokens(text: str) -> int:
    """Rough chars/4 heuristic for budget reporting, not billing."""

    return len(text) // 4


def _read_bounded(path: Path, limit: int) -> tuple[str, bool]:
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return "", True
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", True
    if len(text) > limit:
        return text[:limit], True
    return text, False


def _resolve_focus(project: Path, focus: str) -> Path:
    try:
        resolved = resolve_within(Path(project), focus)
    except LifecycleError as error:
        raise KnowledgeError("KNOWLEDGE_BAD_LOCATOR",
                             f"focus escapes the project: {focus!r}") from error
    return resolved


def _nearest_context(start: Path, root: Path, name: str) -> Path | None:
    """First `name` walking up from start to root. Pure path walk."""

    current = start if start.is_dir() else start.parent
    while True:
        candidate = current / name
        if candidate.is_file():
            return candidate
        if current == root:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def deterministic_items(project: Path, focus_paths: list[str],
                        adr_refs: list[str], excerpt_limit: int) -> list[BundleItem]:
    """AGENTS.md, nearest AI_CONTEXT.md, AI_SUMMARY.md, named ADRs. Read-only."""

    root = Path(project).resolve()
    items: list[BundleItem] = []
    seen: set[str] = set()

    def _take(path: Path, kind: str, weight: int) -> None:
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        text, skipped = _read_bounded(path, excerpt_limit)
        if skipped and not text:
            return
        items.append(BundleItem(label=CANONICAL, kind=kind,
                                locator=_locator(root, path),
                                excerpt=text, score=weight,
                                truncated=skipped))

    agents = root / "AGENTS.md"
    if agents.is_file():
        _take(agents, "AGENTS.md", WEIGHTS["AGENTS.md"])
    for focus in focus_paths:
        resolved = _resolve_focus(root, focus)
        nearest = _nearest_context(resolved, root, "AI_CONTEXT.md")
        if nearest is not None:
            bonus = SCOPE_BONUS if focus != "." else 0
            _take(nearest, "AI_CONTEXT.md", WEIGHTS["AI_CONTEXT.md"] + bonus)
    summary = root / "AI_SUMMARY.md"
    if summary.is_file():
        _take(summary, "AI_SUMMARY.md", WEIGHTS["AI_SUMMARY.md"])
    for ref in adr_refs:
        adr = _resolve_adr(root, ref)
        _take(adr, "ADR", WEIGHTS["ADR"])
    return items


def _resolve_adr(root: Path, ref: str) -> Path:
    """`0017`, `0017-slug` or a docs/adr-relative path. Refuses the rest."""

    locator = validate_locator(ref)
    directory = root / "docs" / "adr"
    if "/" not in locator and not locator.endswith(".md"):
        matches = sorted(directory.glob(f"{locator}*.md"))
        if len(matches) == 1:
            return matches[0]
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             f"ADR ref {ref!r} matches {len(matches)} files")
    resolved = _resolve_focus(root, f"docs/adr/{locator}" if "/" not in locator else locator)
    if not resolved.is_file() or resolved.suffix != ".md":
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             f"ADR ref {ref!r} is not a readable ADR")
    return resolved


def _locator(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def candidate_items(project: Path, focus_paths: list[str],
                    excerpt_limit: int, max_candidates: int) -> list[BundleItem]:
    """Non-terminal candidates as explicitly UNVERIFIED notes. Read-only."""

    try:
        records = storelib.read_all(project)
    except KnowledgeError:
        return []
    root = Path(project).resolve()
    foci = [str(_resolve_focus(root, focus)) for focus in focus_paths]
    scored = []
    for record in records:
        if record["status"] in TERMINAL:
            continue
        module = record["scope"].get("module") or ""
        bonus = SCOPE_BONUS if module and any(module in focus for focus in foci) else 0
        strong = 10 if record["status"] in ("SUPPORTED", "READY_FOR_PROMOTION") else 0
        excerpt = (f"[{record['status']}/{record['kind']}] {record['claim']}"
                   f" ({len(record['evidence'])} evidence)")
        scored.append((WEIGHTS["candidate"] + bonus + strong, record, excerpt))
    scored.sort(key=lambda entry: -entry[0])
    items = []
    for score, record, excerpt in scored[:max_candidates]:
        clipped, truncated = (excerpt[:excerpt_limit], True) if len(excerpt) > excerpt_limit \
            else (excerpt, False)
        items.append(BundleItem(label=UNVERIFIED, kind="candidate",
                                locator=record["candidate_id"], excerpt=clipped,
                                score=score, truncated=truncated))
    return items


@dataclass
class ContextBundle:
    project: str
    focus: list[str] = field(default_factory=list)
    task_type: str = "general"
    items: list[BundleItem] = field(default_factory=list)
    dropped: int = 0
    total_bytes: int = 0
    estimated_tokens: int = 0
    recall: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def to_record(self) -> dict[str, Any]:
        return {"project": self.project, "focus": self.focus,
                "task_type": self.task_type,
                "items": [item.to_record() for item in self.items],
                "dropped": self.dropped, "total_bytes": self.total_bytes,
                "estimated_tokens": self.estimated_tokens,
                "recall": self.recall, "generated_at": self.generated_at}

    def render(self) -> str:
        lines = [f"context bundle: {len(self.items)} item(s), "
                 f"{self.total_bytes} bytes (~{self.estimated_tokens} tokens), "
                 f"{self.dropped} dropped by budget"]
        for item in self.items:
            flag = " [truncated]" if item.truncated else ""
            first = item.excerpt.splitlines()[0] if item.excerpt else "-"
            lines.append(f"  [{item.score:>3}] {item.label} {item.locator}{flag}")
            lines.append(f"         {first[:100]}")
        if self.recall.get("requested") and not self.recall.get("fulfilled"):
            lines.append(f"  recall unavailable: {self.recall.get('reason')}")
        return "\n".join(lines)


def assemble(project: Path, *, focus: list[str] | None = None,
             task_type: str = "general", adr_refs: list[str] | None = None,
             recall: str | None = None,
             budgets: Budgets | None = None) -> ContextBundle:
    """Deterministic planner: collect, rank, bound. No semantic calls."""

    limits = budgets or Budgets()
    focus_paths = focus or ["."]
    items = deterministic_items(Path(project), focus_paths, adr_refs or [],
                                limits.max_excerpt_chars)
    items += candidate_items(Path(project), focus_paths, limits.max_excerpt_chars,
                             limits.max_candidates)
    items.sort(key=lambda item: -item.score)
    kept: list[BundleItem] = []
    used = 0
    for item in items:
        size = len(item.excerpt.encode("utf-8"))
        if len(kept) >= limits.max_items or used + size > limits.max_bytes:
            continue
        kept.append(item)
        used += size
    recall_record: dict[str, Any] = {"requested": recall,
                                     "fulfilled": False,
                                     "provider": None,
                                     "reason": None}
    if recall:
        recall_record["reason"] = "no semantic provider registered (K5b)"
    bundle = ContextBundle(project=str(project), focus=focus_paths,
                           task_type=task_type, items=kept,
                           dropped=len(items) - len(kept), total_bytes=used,
                           estimated_tokens=estimate_tokens(
                               "".join(item.excerpt for item in kept)),
                           recall=recall_record, generated_at=now())
    return bundle


__all__ = ["CANONICAL", "UNVERIFIED", "EXTERNAL", "WEIGHTS", "SCOPE_BONUS",
           "Budgets", "BundleItem", "estimate_tokens", "deterministic_items",
           "candidate_items", "ContextBundle", "assemble"]