"""Provider contracts: structural and semantic recall, always optional.

Providers are INJECTED (`RetrievalProviders`), never global — the
no-global-state rule applies to memory too. Every provider reports a
`probe()` string: either usable or the exact reason it is not. The
assembler treats any provider failure as degraded mode (deterministic
context plus a status), never as a hard error, and canonical weights
always stay above provider scores. Harness-side adapters (a real Smart
Connections bridge, a live Graphify daemon) implement these protocols;
in-repo, `GraphFileProvider` reads the `graphify-out/graph.json` file
the existing pretool hook already points at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class GraphNeighbor:
    path: str
    relation: str = "related"
    distance: int = 1

    def to_record(self) -> dict[str, Any]:
        return {"path": self.path, "relation": self.relation,
                "distance": self.distance}


@dataclass
class SemanticHit:
    locator: str
    score: float = 0.0
    excerpt: str = ""
    external: bool = False

    def to_record(self) -> dict[str, Any]:
        return {"locator": self.locator, "score": self.score,
                "excerpt": self.excerpt, "external": self.external}


class GraphProvider(Protocol):
    """Structural code relationships. Direction: neighbors of a focus file."""

    name: str

    def probe(self) -> str:
        """Usable, or the exact reason it is not."""
        ...  # pragma: no cover - protocol

    def neighbors(self, path: str, *, max_neighbors: int = 10) -> list[GraphNeighbor]:
        ...  # pragma: no cover - protocol


class SemanticProvider(Protocol):
    """Semantic note recall. Scores are 0..1; the assembler caps their weight."""

    name: str

    def probe(self) -> str:
        ...  # pragma: no cover - protocol

    def search(self, query: str, *, limit: int = 5) -> list[SemanticHit]:
        ...  # pragma: no cover - protocol


@dataclass
class RetrievalProviders:
    graph: GraphProvider | None = None
    semantic: SemanticProvider | None = None


def _node_id(node: Any) -> str | None:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        for key in ("id", "path", "file"):
            value = node.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _edge_ends(edge: Any) -> tuple[str, str, str] | None:
    if not isinstance(edge, dict):
        return None
    first = edge.get("source", edge.get("from", edge.get("a")))
    second = edge.get("target", edge.get("to", edge.get("b")))
    if not isinstance(first, str) or not isinstance(second, str):
        return None
    relation = edge.get("type", edge.get("relation", "related"))
    return first, second, str(relation)


class GraphFileProvider:
    """Best-effort reader for `graphify-out/graph.json` (nodes/edges shape).

    Accepts node ids as strings or `{id|path|file}` objects and edges as
    `{source|from|a, target|to|b}` pairs. Anything else — missing file,
    unparsable JSON, unknown shape — reports unavailable through `probe`
    instead of raising, so retrieval degrades deterministically.
    """

    name = "graphify-out/graph.json"

    def __init__(self, project: Path) -> None:
        self.project = Path(project)
        self._error: str | None = None
        self._adjacency: dict[str, list[tuple[str, str]]] = {}
        self._load()

    def _load(self) -> None:
        path = self.project / "graphify-out" / "graph.json"
        if not path.is_file():
            self._error = "graphify-out/graph.json not present"
            return
        try:
            if path.stat().st_size > 8 * 1024 * 1024:
                self._error = "graph file exceeds 8 MiB"
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            self._error = f"graph file unreadable: {error}"
            return
        nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
        edges = payload.get("edges", []) if isinstance(payload, dict) else []
        known = {identity for node in nodes if (identity := _node_id(node))}
        if not known or not isinstance(edges, list):
            self._error = "graph file has no nodes/edges shape"
            return
        for edge in edges:
            parsed = _edge_ends(edge)
            if parsed is None:
                continue
            first, second, relation = parsed
            if first in known and second in known:
                self._adjacency.setdefault(first, []).append((second, relation))
                self._adjacency.setdefault(second, []).append((first, relation))
        if not self._adjacency:
            self._error = "graph file holds no usable edges"

    def probe(self) -> str:
        if self._error is not None:
            return f"unavailable: {self._error}"
        nodes = len(self._adjacency)
        edges = sum(len(peers) for peers in self._adjacency.values()) // 2
        return f"available ({nodes} nodes, {edges} edges)"

    @property
    def available(self) -> bool:
        return self._error is None

    def _match(self, wanted: str) -> str | None:
        if wanted in self._adjacency:
            return wanted
        base = wanted.rsplit("/", 1)[-1]
        for identity in self._adjacency:
            if identity == wanted or identity.rsplit("/", 1)[-1] == base:
                return identity
        return None

    def neighbors(self, path: str, *, max_neighbors: int = 10) -> list[GraphNeighbor]:
        if not self.available:
            return []
        start = self._match(path)
        if start is None:
            return []
        seen = {start}
        frontier = [(start, 0)]
        found: list[GraphNeighbor] = []
        while frontier and len(found) < max_neighbors:
            current, distance = frontier.pop(0)
            for peer, relation in sorted(self._adjacency.get(current, [])):
                if peer in seen:
                    continue
                seen.add(peer)
                found.append(GraphNeighbor(path=peer, relation=relation,
                                           distance=distance + 1))
                frontier.append((peer, distance + 1))
                if len(found) >= max_neighbors:
                    break
        return found


__all__ = ["GraphNeighbor", "SemanticHit", "GraphProvider", "SemanticProvider",
           "RetrievalProviders", "GraphFileProvider"]