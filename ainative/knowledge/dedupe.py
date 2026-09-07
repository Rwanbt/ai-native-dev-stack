"""Deduplication: exact, containment and lexical-overlap relations.

Semantic similarity alone never decides equivalence (INV-04): every
relation below carries a deterministic, human-reviewable explanation,
and anything that is not an exact match or a containment stays
human-gated (CONFLICTS with class SEMANTIC_AMBIGUITY, or UNRELATED).
A real semantic provider (Smart Connections) plugs in at K5 behind this
same output contract; nothing here assumes one is present.
"""

from __future__ import annotations

import re
from pathlib import Path

NEW = "NEW"
DUPLICATE = "DUPLICATE"
REFINEMENT = "REFINEMENT"
SUPERSEDES = "SUPERSEDES"
CONFLICTS = "CONFLICTS"
UNRELATED = "UNRELATED"

OVERLAP_AMBIGUOUS = 0.6
MAX_SCAN_TARGETS = 20
MAX_SCAN_BYTES = 512 * 1024

_CANONICAL_HINTS = (
    ("AGENTS.md", ("AGENTS.md",)),
    ("KNOWN_FAILURE_PATTERNS.md", ("KNOWN_FAILURE_PATTERNS.md", "KNOWN_FAILURE_PATTERNS")),
    ("AI_CONTEXT.md", ("AI_CONTEXT.md", "AI_CONTEXT")),
    ("docs/adr/", ("docs/adr", "ADR")),
)


def normalize(text: str) -> str:
    """Lowercase, punctuation-blind, whitespace-collapsed. Pure function."""

    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def token_overlap(first: str, second: str) -> float:
    """Jaccard similarity over normalized tokens. Pure function."""

    left, right = set(normalize(first).split()), set(normalize(second).split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def classify_pair(claim: str, target: str, other_claim: str,
                  other_target: str) -> tuple[str, float, str]:
    """One relation plus score plus explanation. Pure function, no I/O."""

    mine, theirs = normalize(claim), normalize(other_claim)
    if mine == theirs:
        return DUPLICATE, 1.0, "normalized claims are identical"
    if mine and mine in theirs:
        return REFINEMENT, 0.9, "this claim is contained in the other; the other refines it"
    if theirs and theirs in mine:
        return REFINEMENT, 0.9, "the other claim is contained in this one; this one refines it"
    score = token_overlap(claim, other_claim)
    if score >= OVERLAP_AMBIGUOUS and target == other_target:
        return (CONFLICTS, score,
                f"token overlap {score:.2f} on the same target ({target}); "
                "a human must separate refinement from contradiction")
    if score >= OVERLAP_AMBIGUOUS:
        return (UNRELATED, score,
                f"token overlap {score:.2f} but different targets "
                f"({target} vs {other_target})")
    return UNRELATED, score, f"token overlap {score:.2f}: no relation"


def find_candidate_relations(candidate: dict, records: list[dict]) -> list[dict]:
    """Relations to every other stored candidate. Read-only."""

    relations = []
    for other in records:
        if other["candidate_id"] == candidate["candidate_id"]:
            continue
        relation, score, explanation = classify_pair(
            candidate["claim"], candidate["target_hint"],
            other["claim"], other["target_hint"])
        if relation != UNRELATED:
            relations.append({"candidate_id": other["candidate_id"],
                              "status": other["status"],
                              "relation": relation, "score": round(score, 3),
                              "explanation": explanation})
    return sorted(relations, key=lambda item: -item["score"])


MIN_RELATED_TOKENS = 5


def scan_canonical_related(project: Path, candidate: dict) -> list[dict]:
    """High-overlap canonical lines that are NOT verbatim (E2E-03 class).

    A verbatim hit is DUPLICATE (handled by `scan_canonical`). A close
    line on the same target may contradict or refine the claim — only a
    human can tell, so it returns SEMANTIC_AMBIGUITY material, never a
    verdict. Threshold equals the candidate-level ambiguity bound.
    """

    wanted = normalize(candidate.get("claim", ""))
    if not wanted:
        return []
    hits = []
    for path in canonical_search_paths(project, candidate.get("target_hint", "")):
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            tokens = normalize(line).split()
            if len(tokens) < MIN_RELATED_TOKENS:
                continue
            score = token_overlap(candidate["claim"], line)
            if score >= OVERLAP_AMBIGUOUS:
                try:
                    locator = path.resolve().relative_to(
                        Path(project).resolve()).as_posix()
                except ValueError:
                    locator = path.name
                hits.append({"path": locator, "score": round(score, 3),
                             "excerpt": line.strip()[:100]})
                break
    return hits


def canonical_search_paths(project: Path, target_hint: str) -> list[Path]:
    """Repo files a target hint maps to. Bounded, read-only, no following."""

    root = Path(project)
    for hint, keys in _CANONICAL_HINTS:
        if hint in target_hint or target_hint in hint:
            if hint == "AI_CONTEXT.md":
                found = sorted(root.glob("**/AI_CONTEXT.md"))
                return [path for path in found[:MAX_SCAN_TARGETS] if path.is_file()]
            if hint == "docs/adr/":
                found = sorted((root / "docs" / "adr").glob("*.md"))
                return [path for path in found[:MAX_SCAN_TARGETS] if path.is_file()]
            candidate = root / hint
            return [candidate] if candidate.is_file() else []
    return []


def scan_canonical(project: Path, candidate: dict) -> list[dict]:
    """Verbatim-or-normalized presence in the canonical target. Read-only."""

    wanted = normalize(candidate["claim"])
    if not wanted:
        return []
    hits = []
    for path in canonical_search_paths(project, candidate["target_hint"]):
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = normalize(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if wanted in text:
            try:
                locator = path.resolve().relative_to(Path(project).resolve()).as_posix()
            except ValueError:
                locator = path.name
            hits.append({"path": locator,
                         "relation": DUPLICATE,
                         "explanation": "claim already present verbatim in canonical target"})
    return hits


__all__ = ["NEW", "DUPLICATE", "REFINEMENT", "SUPERSEDES", "CONFLICTS", "UNRELATED",
           "OVERLAP_AMBIGUOUS", "MAX_SCAN_TARGETS", "MAX_SCAN_BYTES",
           "normalize", "token_overlap", "classify_pair",
           "find_candidate_relations", "canonical_search_paths", "scan_canonical",
           "scan_canonical_related", "MIN_RELATED_TOKENS"]