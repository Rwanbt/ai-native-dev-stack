#!/usr/bin/env python3
"""
module_discovery.py — Shared module detection logic (single source of truth).

Single source of truth for finding the nearest AI_CONTEXT.md ancestor.
Imported by update_on_edit.py and assemble_context.py.

Previously each of those scripts carried its own divergent copy with different
signatures (str vs Path) and different stop-boundary sets (STOP_DIRS).
"""

from __future__ import annotations  # PEP 563 — keep `Path | None` valid on Python 3.8/3.9

from pathlib import Path

from source_config import EXCLUDE_DIRS


def find_module(file_path: "Path | str") -> "Path | None":
    """
    Walk up from file_path to find the nearest directory containing AI_CONTEXT.md.
    Stops at a .git boundary, filesystem root, or an EXCLUDE_DIRS entry.

    Returns the module directory (Path) or None if not found.
    Accepts both str and Path for compatibility with callers on both sides.
    """
    try:
        current = Path(file_path).resolve().parent
    except Exception:
        return None

    visited: set[Path] = set()
    while current not in visited:
        visited.add(current)
        if (current / "AI_CONTEXT.md").exists():
            return current
        if (current / ".git").exists() or current == current.parent:
            return None
        if current.name in EXCLUDE_DIRS:
            return None
        current = current.parent
    return None
