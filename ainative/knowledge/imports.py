"""Cross-harness import: stage foreign learnings as candidates, never truth.

Convergence row 7. Identity is NEVER synthesized here: every item must carry
an identity_key that this adapter validates through the current identity
grammar (identity.parse_identity) and refuses otherwise - wrong project,
unknown module, unknown shared root and unknown scope all deny. Preview-first
is structural: without --apply nothing is written; with it, valid items are
staged as PENDING candidates through the existing store and every refused
item (missing/ambiguous identity, secret, malformed, unknown kind) is
reported, never silently dropped. The secret quarantine and the bounds are
enforced by the owners before any persistence, so a detected secret yields
zero persistence. Imports never touch canonical files and never promote.

Frozen identity contract (Wave 4):
- origin_harness: claude | codex | opencode | gemini | cursor | minimax | unknown
- origin_project / origin_repository / origin_session: operator-supplied
  provenance, preserved when given, never inferred from cwd
- target project and scope: resolved through the current identity owner
- duplicate imports: candidates only; dedup/support stays owned by resolution
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from . import assertions as assertionslib
from . import identity as identitylib
from . import quarantine as quarantinelib
from . import states as stateslib
from . import store as storelib
from .errors import KnowledgeError

HARNESSES = frozenset({"claude", "codex", "opencode", "gemini", "cursor",
                       "minimax", "unknown"})
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
    """`- claim` bullets. No identity key yet: triage decides, identity refuses."""

    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            claim = stripped[2:].strip()
            if claim:
                items.append({"claim": claim})
    return items


def parse_json(text: str) -> list[dict[str, Any]]:
    """Array of {claim, identity_key?, kind?, module?, session?, evidence?}."""

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
                      "identity_key": entry.get("identity_key"),
                      "kind": entry.get("kind"),
                      "module": entry.get("module"),
                      "session": entry.get("session")})
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


def _check_harness(harness: str) -> None:
    if harness not in HARNESSES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown harness {harness!r} (known: {sorted(HARNESSES)})")


def _resolve(item: dict[str, Any], *, project_slug: str, modules, shared_roots) -> dict[str, Any]:
    """Resolve identity and scope through the current owner; refuse otherwise."""

    key = item.get("identity_key")
    if not key:
        raise KnowledgeError("KNOWLEDGE_IDENTITY_KEY_INVALID",
                             "identity_key is required; import never synthesizes identity")
    identity = identitylib.parse_identity(
        key, modules=frozenset(modules), project_slug=project_slug,
        shared_roots=frozenset(shared_roots))
    quarantinelib.check(item["claim"], purpose="knowledge import")
    return {"claim": item["claim"],
            "identity": identity,
            "scope": identity.scope,
            "kind": str(item.get("kind") or "unclassified"),
            "module": item.get("module"),
            "session": item.get("session")}


def preview(source: Path, *, harness: str, project_slug: str,
            modules=(), shared_roots=(), actor: str = "operator",
            format: str = "auto") -> dict[str, Any]:
    """What `--apply` would stage. Reads and resolves only, writes nothing."""

    _check_harness(harness)
    items = parse(Path(source), format=format)
    staged, refused = [], []
    for item in items:
        try:
            resolved = _resolve(item, project_slug=project_slug,
                                modules=modules, shared_roots=shared_roots)
        except KnowledgeError as error:
            refused.append({"claim": item["claim"][:80],
                            "reason": f"{error.code}: {error.message}"})
            continue
        staged.append({"claim": resolved["claim"], "kind": resolved["kind"],
                       "identity_key": resolved["identity"].key,
                       "scope": resolved["scope"],
                       "module": resolved["module"]})
    return {"harness": harness, "source": str(source), "parsed": len(items),
            "actor": actor, "staged": staged, "refused": refused}


def apply(project: Path, source: Path, *, harness: str, project_slug: str,
          modules=(), shared_roots=(), actor: str = "operator",
          origin_project: str | None = None,
          origin_repository: str | None = None,
          origin_session: str | None = None,
          format: str = "auto") -> dict[str, Any]:
    """Stage valid items as PENDING import candidates. Reports every refusal."""

    _check_harness(harness)
    items = parse(Path(source), format=format)
    created, refused = [], []
    for item in items:
        try:
            resolved = _resolve(item, project_slug=project_slug,
                                modules=modules, shared_roots=shared_roots)
        except KnowledgeError as error:
            refused.append({"claim": item["claim"][:80],
                            "reason": f"{error.code}: {error.message}"})
            continue
        identity = resolved["identity"]
        attested = identitylib.attest(identity, actor=actor)
        value = {"type": "string", "value": resolved["claim"]}
        hashed = assertionslib.assertion_hash(identity, identity.scope, value)
        stamp = statelib.now()
        session = origin_session or resolved.get("session")
        source_record: dict[str, Any] = {"origin": f"import_{harness}",
                                         "harness": harness}
        if session:
            source_record["session"] = session
        provenance: dict[str, Any] = {"actor": actor, "origin": f"import_{harness}",
                                      "harness": harness,
                                      "identity_confirmed_by": attested["confirmed_by"]}
        if origin_project:
            provenance["origin_project"] = origin_project
        if origin_repository:
            provenance["origin_repository"] = origin_repository
        if session:
            provenance["origin_session"] = session
        record = {"schema_version": 1,
                  "candidate_id": statelib.new_identifier("cand"),
                  "kind": resolved["kind"],
                  "state": stateslib.PENDING,
                  "created_at": stamp, "updated_at": stamp,
                  "source": source_record,
                  "scope": {"project": project_slug, "resolved": resolved["scope"]},
                  "claim": resolved["claim"],
                  "identity": {"identity_key": identity.key,
                               "identity_key_grammar_version":
                                   identitylib.IDENTITY_GRAMMAR_VERSION},
                  "assertion_hash": hashed["assertion_hash"],
                  "assertion_normalization_version":
                      assertionslib.NORMALIZATION_VERSION,
                  "hash_algorithm": assertionslib.HASH_ALGORITHM,
                  "assertion_value": hashed["value"],
                  "provenance": provenance}
        try:
            stored = storelib.append_candidate(Path(project), record)
        except KnowledgeError as error:
            refused.append({"claim": item["claim"][:80],
                            "reason": f"{error.code}: {error.message}"})
            continue
        created.append(stored["candidate_id"])
    return {"harness": harness, "source": str(source), "actor": actor,
            "created": created, "refused": refused}


__all__ = ["HARNESSES", "MAX_IMPORT_ITEMS", "MAX_IMPORT_BYTES",
           "parse_markdown", "parse_json", "parse", "preview", "apply"]
