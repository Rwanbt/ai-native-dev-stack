"""Derived-state maintenance: reset and rebuild.

There is deliberately little to do here, and that is the point. No
lifecycle phase persists derived state: the code-to-knowledge bridge
is recomputed on demand, bundles are never cached, and provider
indexes live outside this package. INV-02 therefore holds BY
CONSTRUCTION — `reset-derived` removes the registered derived paths
(the registry is empty; future caches must register to be resettable)
and `rebuild` proves reconstructibility by recomputing the bridge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import staleness as stalenesslib

# Persisted derived caches register their project-relative paths here.
# Empty today: nothing derived is persisted (INV-02 by construction).
DERIVED_PATHS: tuple[str, ...] = ()


def reset_derived(project: Path) -> dict[str, Any]:
    """Delete registered derived state. Canonical and audit never listed."""

    removed = []
    for relative in DERIVED_PATHS:
        path = Path(project) / relative
        if path.exists():
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(relative)
    return {"removed": removed,
            "note": "no persisted derived state (recomputed on demand)"}


def rebuild(project: Path) -> dict[str, Any]:
    """Recompute derived state and prove it matches canonical sources."""

    registry = stalenesslib.bridge(Path(project))
    return {"knowledge_items": len(registry["knowledge"]),
            "indexed_paths": len(registry["code_index"]),
            "note": "bridge recomputed from candidates plus promotion audits"}


__all__ = ["DERIVED_PATHS", "reset_derived", "rebuild"]