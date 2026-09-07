"""GraphProvider: bounded structural neighborhood over graphify output.

Derived-only and read-only: this module never writes canonical state,
never assigns authority (results carry a configured ceiling), and never
reimplements selection — it emits planner source records for the single
ContextPlanner. Every neighbor path is resolved against the active
project root; outside-root results DROP (B2 S16). Missing, oversized or
malformed graph files degrade to unavailable with a reason — the planner
works without them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TRUST_ORDER = ("UNTRUSTED", "DERIVED", "HISTORICAL_OBSERVATION",
               "INFORMATIVE_RESEARCH", "BEHAVIOURAL_EVIDENCE",
               "IMPLEMENTATION_FACT", "FAILURE_PREVENTION",
               "MODULE_CONSTRAINT", "ARCHITECTURE_DECISION",
               "ENGINEERING_POLICY")

DEFAULT_CEILING = "INFORMATIVE_RESEARCH"
MAX_GRAPH_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_NEIGHBORS = 12
DEFAULT_EXCERPT_CHARS = 2000


def cap_domain(domain: str, ceiling: str) -> str:
    """Lower a domain to a ceiling. Pure function."""

    order = list(TRUST_ORDER)
    if domain not in order or ceiling not in order:
        return "UNTRUSTED"
    if order.index(domain) > order.index(ceiling):
        return ceiling
    return domain


class FileGraphProvider:
    """Structural neighborhoods from `graphify-out/graph.json`."""

    def __init__(self, project_root: Path | str, *,
                 graph_path: Path | str | None = None,
                 authority_ceiling: str = DEFAULT_CEILING) -> None:
        self.root = Path(project_root).resolve()
        self.graph_path = Path(graph_path) if graph_path is not None \
            else self.root / "graphify-out" / "graph.json"
        self.ceiling = authority_ceiling if authority_ceiling in TRUST_ORDER \
            else DEFAULT_CEILING
        self._error: str | None = None
        self._nodes: dict[str, dict] = {}
        self._adjacency: dict[str, list[tuple[str, str, float]]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if not self.graph_path.is_file():
                self._error = "graph file absent"
                return
            if self.graph_path.stat().st_size > MAX_GRAPH_BYTES:
                self._error = "graph file exceeds size bound"
                return
            payload = json.loads(self.graph_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            self._error = f"graph file unreadable: {error}"
            return
        if not isinstance(payload, dict):
            self._error = "graph file has no object shape"
            return
        nodes = payload.get("nodes", [])
        links = payload.get("links", payload.get("edges", []))
        if not isinstance(nodes, list) or not isinstance(links, list):
            self._error = "graph file has no nodes/links shape"
            return
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                self._nodes[node["id"]] = node
        for link in links:
            if not isinstance(link, dict):
                continue
            first = link.get("source")
            second = link.get("target")
            if not isinstance(first, str) or not isinstance(second, str):
                continue
            if first not in self._nodes or second not in self._nodes:
                continue
            relation = str(link.get("relation", link.get("type", "related")))
            try:
                weight = float(link.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            self._adjacency.setdefault(first, []).append((second, relation, weight))
            self._adjacency.setdefault(second, []).append((first, relation, weight))

    def capabilities(self) -> dict[str, Any]:
        return {"structural_neighborhood": True, "writes": False,
                "authority": "none, capped at " + self.ceiling}

    def health(self) -> dict[str, Any]:
        self._load()
        if self._error is not None:
            return {"available": False, "reason": self._error,
                    "nodes": 0, "edges": 0}
        edges = sum(len(peers) for peers in self._adjacency.values()) // 2
        return {"available": True, "nodes": len(self._nodes), "edges": edges}

    def probe(self) -> str:
        report = self.health()
        if not report["available"]:
            return f"unavailable: {report['reason']}"
        return (f"available ({report['nodes']} nodes, {report['edges']} edges, "
                f"ceiling {self.ceiling})")

    def _match(self, focus: str) -> list[str]:
        """Node ids matching a repo-relative focus path. Pure lookup."""

        wanted = focus.replace("\\", "/").lstrip("/")
        matched = []
        for identity, node in self._nodes.items():
            source_file = str(node.get("source_file", "")).replace("\\", "/")
            if source_file == wanted or identity == wanted:
                matched.append(identity)
        if not matched:
            base = wanted.rsplit("/", 1)[-1]
            for identity, node in self._nodes.items():
                source_file = str(node.get("source_file", "")).replace("\\", "/")
                if source_file.rsplit("/", 1)[-1] == base and base:
                    matched.append(identity)
        return matched

    def _contained(self, source_file: str) -> Path | None:
        """Resolved in-project path, or None (DROP per B2 S16)."""

        if not source_file or "://" in source_file:
            return None
        candidate = (self.root / source_file.replace("\\", "/"))
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
        try:
            resolved.relative_to(self.root)
        except ValueError:
            return None
        if not resolved.is_file():
            return None
        return resolved

    def neighbors(self, focus: str, *, max_neighbors: int = DEFAULT_MAX_NEIGHBORS,
                  min_weight: float = 0.0) -> tuple[list[dict[str, Any]], dict]:
        """Bounded neighbor records plus a drop report. Never raises."""

        self._load()
        report: dict[str, Any] = {"dropped_outside_root": 0,
                                  "dropped_unreadable": 0,
                                  "reason": self._error}
        if self._error is not None:
            return [], report
        seen: dict[str, dict[str, Any]] = {}
        for identity in self._match(focus):
            for peer, relation, weight in self._adjacency.get(identity, []):
                if weight < min_weight:
                    continue
                known = seen.get(peer)
                if known is None or weight > known["weight"]:
                    seen[peer] = {"id": peer, "relation": relation,
                                  "weight": weight}
        ranked = sorted(seen.values(), key=lambda item: -item["weight"])
        records = []
        for entry in ranked[: max(0, max_neighbors)]:
            node = self._nodes[entry["id"]]
            path = self._contained(str(node.get("source_file", "")))
            if path is None:
                report["dropped_outside_root"] += 1
                continue
            records.append({"node_id": entry["id"], "path": path,
                            "relation": entry["relation"],
                            "weight": entry["weight"]})
        return records, report


def structural_sources(provider: FileGraphProvider, focus: str, *,
                       max_neighbors: int = DEFAULT_MAX_NEIGHBORS,
                       excerpt_chars: int = DEFAULT_EXCERPT_CHARS
                       ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Neighbor files as Tier C planner sources under the ceiling."""

    neighbors, report = provider.neighbors(focus, max_neighbors=max_neighbors)
    sources = []
    for entry in neighbors:
        try:
            text = entry["path"].read_text(encoding="utf-8", errors="replace")
        except OSError:
            report["dropped_unreadable"] += 1
            continue
        excerpt = text[:excerpt_chars]
        sources.append({"kind": "code",
                        "locator": entry["path"].relative_to(
                            provider.root).as_posix(),
                        "scope": "repository",
                        "excerpt": excerpt,
                        "authority_domain": cap_domain("IMPLEMENTATION_FACT",
                                                       provider.ceiling),
                        "tier": "C",
                        "freshness": "UNKNOWN"})
    report["returned"] = len(sources)
    return sources, report


__all__ = ["TRUST_ORDER", "DEFAULT_CEILING", "MAX_GRAPH_BYTES",
           "DEFAULT_MAX_NEIGHBORS", "DEFAULT_EXCERPT_CHARS",
           "cap_domain", "FileGraphProvider", "structural_sources"]
