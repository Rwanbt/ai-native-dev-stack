"""Project scope registry and physical source resolution (B2 S16-S17).

Metadata alone is never sufficient: every retrieved source must resolve
to a real path inside the active project root (or an explicitly
configured shared root with explicit permission), or it DROPs with a
recorded reason. Claimed scopes are hints, never verdicts — a note
physically outside the project claiming project metadata still DROPs,
and finer-than-project claimed scopes downgrade to the verified project
scope until a module registry exists to check them against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectRegistry:
    """Explicit configuration. Never inferred from results."""

    project_root: Path
    project_slug: str
    shared_roots: dict[str, Path] = field(default_factory=dict)

    def resolved(self) -> "ProjectRegistry":
        """Normalized copy: all roots fully resolved (symlinks, case)."""

        return ProjectRegistry(
            project_root=self.project_root.resolve(),
            project_slug=self.project_slug,
            shared_roots={name: Path(path).resolve()
                          for name, path in self.shared_roots.items()})


def _real_path(source: dict) -> Path | None:
    """The claimed filesystem location, or None when absent/unresolvable."""

    raw = source.get("source_path", source.get("path", ""))
    if not isinstance(raw, str) or not raw or "://" in raw:
        return None
    # Absolute only: a relative path would resolve against the process
    # working directory, manufacturing trust out of ambient state.
    if not Path(raw).is_absolute():
        return None
    try:
        resolved = Path(raw).resolve()
    except OSError:
        return None
    if not resolved.exists():
        return None
    return resolved


def resolve_source(source: dict, *, registry: ProjectRegistry,
                   shared_allowed: bool = False) -> tuple[str | None, str]:
    """Verified scope or (None, DROP reason). Pure apart from resolution."""

    if not isinstance(source, dict):
        return None, "not a source object"
    registry = registry.resolved()
    path = _real_path(source)
    if path is None:
        return None, "no resolvable source path"
    try:
        path.relative_to(registry.project_root)
        return f"project/{registry.project_slug}", "verified project scope"
    except ValueError:
        pass
    if shared_allowed:
        for name, root in registry.shared_roots.items():
            try:
                path.relative_to(root)
                return f"global/{name}", "verified shared scope"
            except ValueError:
                continue
        return None, "outside project and shared roots"
    return None, "outside active project root"


def filter_results(results: list[dict], *, registry: ProjectRegistry,
                   shared_allowed: bool = False) -> tuple[list[dict], list[dict]]:
    """Keep verified sources, DROP the rest with reasons. Pure apart from I/O."""

    kept, dropped = [], []
    for record in results:
        if not isinstance(record, dict):
            dropped.append({"locator": "?", "reason": "not a source object"})
            continue
        scope, reason = resolve_source(record, registry=registry,
                                       shared_allowed=shared_allowed)
        locator = str(record.get("locator", record.get("source_path", "?")))
        if scope is None:
            dropped.append({"locator": locator, "reason": reason})
            continue
        kept.append({**record, "scope": scope,
                     "scope_reason": reason})
    return kept, dropped


__all__ = ["ProjectRegistry", "resolve_source", "filter_results"]
