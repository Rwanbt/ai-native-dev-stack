"""Derived-state maintenance: compose owners, never a parallel orchestrator.

Convergence row 8. This module inspects and (only with --apply-safe) prunes
categories that are explicitly transient and owned elsewhere:

- expired working checkpoints -> continuity.prune_expired (owner)
- registered derived paths   -> reset-derived, registry is empty by design;
  future caches MUST register here to become resettable (INV-02 by
  construction)

It NEVER rewrites canonical Markdown, never touches audit receipts, never
deletes candidate/support stores (Git-trackable knowledge), never promotes
and never moves data across vaults or domains. Every potentially destructive
action defaults to a dry-run plan.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import continuity as continuitylib
from . import paths as controlpaths

DERIVED_PATHS: tuple[str, ...] = ()
EXPORT_SCHEMA_VERSION = 1
STORES = (("state", "state/knowledge", ("candidates.jsonl", "supports.jsonl")),
          ("audit", "audit/knowledge", ("audit.jsonl",)))


def inspect(project: Path) -> dict[str, Any]:
    """Measured health footprint. No thresholds invented, no writes."""

    root = Path(project)
    controlpaths.ensure_contained(root)
    state = controlpaths.state_dir(root)
    files: dict[str, Any] = {}
    for label, relative, names in STORES:
        for name in names:
            path = root / ".ai-native" / relative / name
            files[f"{label}:{name}"] = path.stat().st_size if path.is_file() else None
    working = continuitylib.checkpoint_status(root)
    return {"working": working,
            "stores": files,
            "derived_registry": list(DERIVED_PATHS)}


def maintain(project: Path, *, apply_safe: bool = False) -> dict[str, Any]:
    """Dry-run by default. --apply-safe removes provably expired checkpoints only."""

    root = Path(project)
    status = continuitylib.checkpoint_status(root)
    plan = {"apply_safe": apply_safe,
            "removable_expired_checkpoints": status["expired"],
            "kept_checkpoints": status["checkpoints"] - status["expired"],
            "candidates_stores": "never pruned by maintenance (Git-trackable knowledge)",
            "audit": "never pruned by maintenance"}
    if not apply_safe:
        plan["action"] = "dry-run; nothing was removed"
        return plan
    outcome = continuitylib.prune_expired(root)
    plan["action"] = "applied-safe"
    plan["removed"] = outcome["removed"]
    plan["kept"] = outcome["kept"]
    return plan


def export(project: Path, target: Path) -> dict[str, Any]:
    """Copy the JSONL stores into a portable bundle with a digest manifest."""

    root = Path(project)
    controlpaths.ensure_contained(root)
    destination = Path(target)
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for label, relative, names in STORES:
        for name in names:
            source = root / ".ai-native" / relative / name
            if not source.is_file():
                continue
            payload = source.read_bytes()
            out = destination / f"{label}_{name}"
            out.write_bytes(payload)
            entries.append({"source": relative + "/" + name,
                            "exported": out.name,
                            "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {"schema_version": EXPORT_SCHEMA_VERSION,
                "project": str(root), "entries": entries}
    (destination / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"exported": len(entries), "target": str(destination),
            "manifest": str(destination / "MANIFEST.json")}


def reset_derived(project: Path, *, apply_safe: bool = False) -> dict[str, Any]:
    """Remove only registered derived paths. Empty registry = nothing to do."""

    root = Path(project)
    controlpaths.ensure_contained(root)
    registered = list(DERIVED_PATHS)
    removable = [str(root / relative) for relative in registered
                 if (root / relative).exists()]
    if not apply_safe:
        return {"dry_run": True, "registered": registered, "removable": removable}
    removed = []
    for relative in registered:
        candidate = root / relative
        if candidate.is_dir():
            import shutil
            shutil.rmtree(candidate, ignore_errors=True)
            removed.append(relative)
        elif candidate.is_file():
            try:
                candidate.unlink()
                removed.append(relative)
            except OSError:
                pass
    return {"dry_run": False, "registered": registered, "removed": removed}


__all__ = ["DERIVED_PATHS", "inspect", "maintain", "export", "reset_derived"]
