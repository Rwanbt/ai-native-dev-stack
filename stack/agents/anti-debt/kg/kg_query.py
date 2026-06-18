"""
kg_query.py — Causal queries on the Knowledge Graph.

Per ADR-0017 (Architecture) and Layer 5 (Knowledge Graph).
All queries are read-only and use indices for O(log n) performance.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from kg_schema import Node, Edge
from kg_store import KgStore


class KgQuery:
    """High-level query interface on the Knowledge Graph."""

    def __init__(self, store: KgStore):
        self.store = store

    # ============================================================
    # Basic queries
    # ============================================================

    def find_debts_affecting_component(
        self, component_name: str, severity: Optional[list[str]] = None
    ) -> list[Node]:
        """Find all debts that affect a component by name.

        Example: "Which critical/high debts affect processAudio?"
        """
        component = self.store.find_nodes(type="Component", name_pattern=component_name)
        if not component:
            return []
        component_ids = [c.id for c in component]

        # Find all debts connected via 'affects' edge
        placeholders = ",".join("?" * len(component_ids))
        sql = f"""
            SELECT DISTINCT n.* FROM nodes n
            JOIN edges e ON e.source_id = n.id
            WHERE e.target_id IN ({placeholders})
              AND e.type = 'affects'
              AND n.type = 'Debt'
        """
        if severity:
            sev_placeholders = ",".join("?" * len(severity))
            sql += f" AND json_extract(n.metadata, '$.severity') IN ({sev_placeholders})"
        params = component_ids + (severity or [])
        rows = self.store.conn.execute(sql, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def find_components_affected_by_debt(self, debt_id: str) -> list[Node]:
        """Find all components affected by a given debt."""
        rows = self.store.conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON e.target_id = n.id
            WHERE e.source_id = ? AND e.type = 'affects' AND n.type = 'Component'
            """,
            (debt_id,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def find_fixes_for_debt(self, debt_id: str) -> list[Node]:
        """Find all fixes that resolve a given debt."""
        rows = self.store.conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON e.source_id = n.id
            WHERE e.target_id = ? AND e.type = 'resolves' AND n.type = 'Fix'
            """,
            (debt_id,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def find_decisions_depending_on_component(self, component_id: str) -> list[Node]:
        """Find all decisions that depend on a component (i.e. would be impacted by changes to it)."""
        rows = self.store.conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON e.source_id = n.id
            WHERE e.target_id = ? AND e.type = 'blocks' AND n.type = 'Decision'
            """,
            (component_id,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def find_adrs_documenting_decision(self, decision_id: str) -> list[Node]:
        """Find all ADRs that document a given decision."""
        rows = self.store.conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON e.source_id = n.id
            WHERE e.target_id = ? AND e.type = 'documents' AND n.type = 'ADR'
            """,
            (decision_id,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    # ============================================================
    # Causal queries (BFS traversal)
    # ============================================================

    def find_root_causes(self, node_id: str, max_depth: int = 5) -> list[list[Node]]:
        """Find all root cause chains leading to a node (BFS reverse).

        Example: "What are the root causes of this bug?"
        Returns a list of causal chains, each chain is a list of nodes
        from the root cause to the target.
        """
        chains: list[list[Node]] = []

        def bfs(target_id: str, path: list[Node], depth: int):
            if depth >= max_depth:
                chains.append(list(reversed(path)))
                return
            # Guard against 'causes' cycles: never revisit a node already on the
            # current path (else a cyclic graph explodes / never terminates).
            on_path = {n.id for n in path[:-1]}
            # Find nodes that "cause" target_id
            causes = self.store.conn.execute(
                """
                SELECT n.* FROM nodes n
                JOIN edges e ON e.source_id = n.id
                WHERE e.target_id = ? AND e.type = 'causes'
                """,
                (target_id,),
            ).fetchall()
            if not causes:
                chains.append(list(reversed(path + [self._get_node_or_none(target_id)])))
                return
            for row in causes:
                cause_node = self._row_to_node(row)
                if cause_node.id in on_path:
                    continue  # cycle — stop this branch
                bfs(cause_node.id, path + [cause_node], depth + 1)

        target = self.store.get_node(node_id)
        if target:
            bfs(node_id, [target], 0)
        return chains

    def find_consequences(self, node_id: str, max_depth: int = 5) -> list[list[Node]]:
        """Find all consequence chains from a node (BFS forward).

        Example: "If I fix this debt, what else changes?"
        """
        chains: list[list[Node]] = []

        def bfs(source_id: str, path: list[Node], depth: int):
            if depth >= max_depth:
                chains.append(list(path))
                return
            on_path = {n.id for n in path[:-1]}  # cycle guard
            consequences = self.store.conn.execute(
                """
                SELECT n.* FROM nodes n
                JOIN edges e ON e.target_id = n.id
                WHERE e.source_id = ? AND e.type = 'causes'
                """,
                (source_id,),
            ).fetchall()
            if not consequences:
                chains.append(list(path))
                return
            for row in consequences:
                target_node = self._row_to_node(row)
                if target_node.id in on_path:
                    continue  # cycle — stop this branch
                bfs(target_node.id, path + [target_node], depth + 1)

        source = self.store.get_node(node_id)
        if source:
            bfs(node_id, [source], 0)
        return chains

    def find_conflicts_for(self, node_id: str) -> list[Node]:
        """Find all nodes that conflict with the given node."""
        rows = self.store.conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON (e.source_id = n.id AND e.target_id = ?)
                          OR (e.target_id = n.id AND e.source_id = ?)
            WHERE e.type = 'conflicts'
            """,
            (node_id, node_id),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def find_superseded_by(self, node_id: str) -> list[Node]:
        """Find all nodes that supersede the given node (newer version)."""
        rows = self.store.conn.execute(
            """
            SELECT n.* FROM nodes n
            JOIN edges e ON e.source_id = n.id
            WHERE e.target_id = ? AND e.type = 'supersedes'
            """,
            (node_id,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    # ============================================================
    # Helpers
    # ============================================================

    def _row_to_node(self, row) -> Node:
        from kg_store import _row_to_node as store_row_to_node
        return store_row_to_node(row)

    def _get_node_or_none(self, node_id: str) -> Optional[Node]:
        return self.store.get_node(node_id)
