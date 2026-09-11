"""SemanticProvider contract (B2 S11/S14). Core functions without one.

A semantic backend is always optional: Smart Connections (or any other
engine) arrives as a harness-side adapter implementing this contract,
and every result still passes physical scope resolution before the
planner ever sees it. No result carries authority by itself; the
configured ceiling caps whatever a provider claims.
"""

from __future__ import annotations

from typing import Any, Protocol


class SemanticProvider(Protocol):
    """Retrieval backend. Metadata is data, never authority."""

    name: str

    def capabilities(self) -> dict[str, Any]:
        """What this backend can do (search, scopes, limits)."""
        ...  # pragma: no cover - contract

    def search(self, query: str, scope: str, limit: int) -> list[dict]:
        """Hits shaped {locator, source_path, excerpt, score, ...}."""
        ...  # pragma: no cover - contract

    def health(self) -> dict[str, Any]:
        """Liveness plus backend detail for doctor output."""
        ...  # pragma: no cover - contract

    def metadata(self) -> dict[str, Any]:
        """execution_scope, data_egress, project_filtering, authority_ceiling."""
        ...  # pragma: no cover - contract


class NoopSemanticProvider:
    """The honest default: no backend configured. Never raises."""

    name = "none"

    def capabilities(self) -> dict[str, Any]:
        return {"search": False, "reason": "no semantic backend configured"}

    def search(self, query: str, scope: str, limit: int) -> list[dict]:
        return []

    def health(self) -> dict[str, Any]:
        return {"available": False, "reason": "no semantic backend configured"}

    def metadata(self) -> dict[str, Any]:
        return {"execution_scope": "none", "data_egress": "none",
                "project_filtering": "none", "authority_ceiling": "UNTRUSTED"}


DEFAULT_CEILING = "INFORMATIVE_RESEARCH"


def search_scoped(provider: Any, query: str, *, registry: Any,
                  scope: str = "", limit: int = 5,
                  ceiling: str = DEFAULT_CEILING,
                  shared_allowed: bool = False,
                  excerpt_chars: int = 2000) -> tuple[list[dict], dict]:
    """Search, then physically verify, cap and map every hit.

    Returns planner-ready sources plus a report (kept, dropped reasons,
    provider health). A faulting backend degrades to empty with a reason;
    it never raises and never bypasses scope resolution.
    """

    from .graph import cap_domain
    from .scope import filter_results

    report: dict[str, Any] = {"provider": getattr(provider, "name", "?"),
                              "dropped": [], "reason": None}
    try:
        hits = provider.search(query, scope, limit)
    except Exception as error:
        report["reason"] = f"backend fault: {type(error).__name__}"
        return [], report
    if not isinstance(hits, list):
        report["reason"] = "backend returned non-list"
        return [], report
    kept, dropped = filter_results(hits, registry=registry,
                                   shared_allowed=shared_allowed)
    report["dropped"] = dropped
    sources = []
    for record in kept[: max(0, limit)]:
        excerpt = str(record.get("excerpt", ""))[:excerpt_chars]
        sources.append({"kind": "note",
                        "locator": str(record.get("locator", "semantic-hit")),
                        "scope": record["scope"],
                        "excerpt": excerpt,
                        "authority_domain": cap_domain(
                            str(record.get("authority_domain",
                                           "HISTORICAL_OBSERVATION")),
                            ceiling),
                        "freshness": str(record.get("freshness", "UNKNOWN")),
                        "provider": getattr(provider, "name", "?")})
    report["returned"] = len(sources)
    return sources, report


__all__ = ["SemanticProvider", "NoopSemanticProvider", "DEFAULT_CEILING",
           "search_scoped"]
