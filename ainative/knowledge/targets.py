"""Promotion targets: from a candidate hint to exactly one repo file.

Narrow safe subset for K4 (plan Phase K4 gate): `AGENTS.md`, the known
failure-patterns file, `AI_CONTEXT.md` files and `docs/adr/*.md`. Vault
notes, session history and transient paths are never promotion targets
from this engine — Vault promotion stays a human edit. Ambiguity (zero
or several files) refuses with KNOWLEDGE_TARGET_UNSUPPORTED and names
the candidates; an explicit `--target` (validated, project-confined,
must exist) disambiguates. ADR targets always allocate a NEW numbered
file; existing ADRs are never edited in place.
"""

from __future__ import annotations

import re
from pathlib import Path

from ainative.lifecycle.paths import resolve_within

from . import dedupe as dedupelib
from .candidate import validate_locator
from .errors import KnowledgeError

_ADR_NUMBER = re.compile(r"^(\d{4})-")


def resolve(project: Path, candidate: dict, *, target: str | None = None) -> Path:
    """Exactly one promotion target file, or a refusal. No I/O beyond checks."""

    root = Path(project)
    if target is not None:
        locator = validate_locator(target)
        resolved = resolve_within(root, locator)
        if not resolved.is_file():
            raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                                 f"explicit target {target!r} is not a file")
        return resolved
    hint = candidate.get("target_hint", "")
    module = candidate.get("scope", {}).get("module")
    if hint.startswith("docs/adr"):
        return _allocate_adr(root, candidate)
    paths = dedupelib.canonical_search_paths(root, hint)
    if module:
        paths = [path for path in paths if module in path.parts]
    if not paths:
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             f"no promotion target for hint {hint!r}"
                             + (f" with module {module!r}" if module else ""),
                             hint=hint)
    if len(paths) > 1:
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             f"ambiguous promotion target for hint {hint!r}; "
                             "narrow with an explicit --target",
                             candidates=sorted(str(path) for path in paths))
    return paths[0]


def next_adr_number(project: Path) -> int:
    """One past the highest ADR number on disk. Deterministic, no I/O beyond list."""

    directory = Path(project) / "docs" / "adr"
    numbers = []
    if directory.is_dir():
        for path in directory.glob("*.md"):
            match = _ADR_NUMBER.match(path.name)
            if match:
                numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def _allocate_adr(project: Path, candidate: dict) -> Path:
    words = dedupelib.normalize(candidate.get("claim", "")).split()[:5]
    slug = "-".join(words)[:40].strip("-") or "candidate"
    return Path(project) / "docs" / "adr" / f"{next_adr_number(project):04d}-{slug}.md"


__all__ = ["resolve", "next_adr_number"]