"""Cross-harness import: stage foreign learnings as candidates, never truth.

Claude, Codex, OpenCode (and later Gemini/Cursor) sessions hold
learnings worth keeping — but an imported observation enters as a
PENDING candidate with `import_<harness>` provenance, never directly
into canonical files (plan Phase K8 gate). Preview-first is structural:
without `--apply` nothing is written; with it, valid items are staged
and every refused item (secret, malformed, unknown kind) is reported,
never silently dropped. The import file is READ from anywhere the user
points at (harness dirs live outside the project); nothing is ever
WRITTEN outside the project store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from . import store as storelib
from .candidate import KINDS, capture
from .errors import KnowledgeError

HARNESSES = frozenset({"claude", "codex", "opencode", "gemini", "cursor"})

MAX_IMPORT_ITEMS = 100
MAX_IMPORT_BYTES = 1024 * 1024


def _read_source(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 f"import file exceeds {MAX_IMPORT_BYTES} bytes; split it")
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"cannot read import file: {error}") from error


def parse_markdown(text: str) -> list[dict[str, Any]]:
    """`- claim` bullets. Kind UNKNOWN, no evidence — triage decides."""

    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            claim = stripped[2:].strip()
            if claim:
                items.append({"claim": claim})
    return items


def parse_json(text: str) -> list[dict[str, Any]]:
    """Array of {claim, kind?, module?, evidence?[{type, locator, digest?}]}."""

    try:
        payload = json.loads(text)
    except ValueError as error:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"import JSON is invalid: {error}") from error
    if not isinstance(payload, list):
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "import JSON must be an array of items")
    items = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict) or not str(entry.get("claim", "")).strip():
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 f"import item {index} has no claim")
        items.append({"claim": str(entry["claim"]).strip(),
                      "kind": entry.get("kind", "UNKNOWN"),
                      "module": entry.get("module"),
                      "evidence": entry.get("evidence", [])})
    return items


def parse(source: Path, *, format: str = "auto") -> list[dict[str, Any]]:
    """Parse without writing. Format auto-detects on file suffix."""

    text = _read_source(Path(source))
    chosen = format
    if chosen == "auto":
        chosen = "json" if str(source).lower().endswith(".json") else "md"
    if chosen == "json":
        items = parse_json(text)
    elif chosen == "md":
        items = parse_markdown(text)
    else:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown import format {format!r}")
    if len(items) > MAX_IMPORT_ITEMS:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"import holds {len(items)} items (max "
                             f"{MAX_IMPORT_ITEMS}); split it")
    return items


def preview(source: Path, *, harness: str,
            format: str = "auto") -> dict[str, Any]:
    """What `--apply` would stage. Reads only, stages nothing."""

    if harness not in HARNESSES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown harness {harness!r} "
                             f"(known: {sorted(HARNESSES)})")
    items = parse(Path(source), format=format)
    staged, refused = [], []
    for item in items:
        kind = str(item.get("kind", "UNKNOWN")).upper()
        if kind not in KINDS:
            refused.append({"claim": item["claim"][:80],
                            "reason": f"unknown kind {item.get('kind')!r}"})
            continue
        staged.append({"claim": item["claim"], "kind": kind,
                       "module": item.get("module"),
                       "evidence": item.get("evidence", []) or []})
    return {"harness": harness, "source": str(source), "parsed": len(items),
            "staged": staged, "refused": refused}


def apply(project: Path, source: Path, *, harness: str, actor: str = "unknown",
          format: str = "auto") -> dict[str, Any]:
    """Stage valid items as PENDING import candidates. Reports the rest."""

    report = preview(source, harness=harness, format=format)
    created, refused = [], list(report["refused"])
    for item in report["staged"]:
        try:
            stored = storelib.append(Path(project), capture(
                project=str(Path(project)), agent=harness,
                session=statelib.new_identifier("import"),
                origin_type=f"import_{harness}", kind=item["kind"],
                claim=item["claim"], module=item.get("module")))
            for evidence in item.get("evidence", []) or []:
                from . import evidence as evidencelib
                evidencelib.add_evidence(Path(project), stored["candidate_id"],
                                         evidence, actor=actor)
            created.append(stored["candidate_id"])
        except KnowledgeError as error:
            refused.append({"claim": item["claim"][:80],
                            "reason": f"{error.code}: {error.message}"})
    return {"harness": harness, "source": str(source),
            "created": created, "refused": refused}


__all__ = ["HARNESSES", "MAX_IMPORT_ITEMS", "MAX_IMPORT_BYTES",
           "parse_markdown", "parse_json", "parse", "preview", "apply"]