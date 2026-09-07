"""Candidate provenance: who observed what, in which repository state.

Deliberately lifecycle-side. Vocabulary reuses Work Plane names
(`git_recorded`, freshness outcomes) with a `knowledge.` scope prefix,
but this module MUST NOT import `ainative_workplane/` (ADR-0011): the
Standard profile operates without loading an authority module. Git
observation here is best-effort context, never verdict evidence — a
repository that cannot be read yields `git_available: False`, not a
failure, because knowledge capture MUST NOT fail where deterministic
context still works (degraded mode, INV-08).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REQUIRED_KEYS = ("project", "repository", "agent", "session", "origin_type",
                 "timestamp", "source_paths", "git_head", "git_dirty")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(root: Path, *arguments: str, timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", "-C", str(root), *arguments],
                              capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def observe_repository(path: str | Path) -> dict[str, Any]:
    """Best-effort repository state for provenance. Never raises."""

    root = Path(path)
    base = root if root.is_dir() else root.parent
    head = _git(base, "rev-parse", "HEAD")
    if head is None or head.returncode != 0 or not head.stdout.strip():
        return {"git_available": False, "git_head": None, "git_dirty": None,
                "git_recorded": False}
    status = _git(base, "status", "--porcelain")
    dirty = bool(status is not None and status.returncode == 0 and status.stdout.strip())
    toplevel = _git(base, "rev-parse", "--show-toplevel")
    repository = (toplevel.stdout.strip() if toplevel is not None and toplevel.returncode == 0
                  and toplevel.stdout.strip() else str(base))
    return {"git_available": True, "git_head": head.stdout.strip(),
            "git_dirty": dirty, "git_recorded": True, "repository": repository}


def build_provenance(*, project: str, agent: str, session: str,
                     origin_type: str, source_paths: Iterable[str] = (),
                     repository: str | Path | None = None,
                     timestamp: str | None = None) -> dict[str, Any]:
    """Assemble the minimum provenance record. Never raises for I/O reasons."""

    observed = observe_repository(repository) if repository is not None else {}
    return {
        "project": project,
        "repository": str(repository) if repository is not None
        else str(observed.get("repository", "")),
        "agent": agent,
        "session": session,
        "origin_type": origin_type,
        "timestamp": timestamp or now(),
        "source_paths": list(source_paths),
        "git_head": observed.get("git_head"),
        "git_dirty": observed.get("git_dirty"),
        "git_available": observed.get("git_available", False),
    }


__all__ = ["REQUIRED_KEYS", "now", "observe_repository", "build_provenance"]