"""
kg_store.py — CRUD operations for the Knowledge Graph.

Per ADR-0023 (Storage V2) — Layer 0.
All operations are idempotent (UPSERT semantics).
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from kg_schema import (
    Node, Edge, init_kg, get_meta, KG_SCHEMA_VERSION,
)


# ============================================================
# Connection management
# ============================================================

class KgStore:
    """Connection wrapper for the Knowledge Graph SQLite database.

    Usage:
        kg = KgStore(Path("~/.mavis/kg.db"))
        kg.init()
        node = Node(type="Component", name="processAudio")
        kg.upsert_node(node)
        ...
    """

    def __init__(self, db_path: Path, timeout: int = 30):
        self.db_path = Path(db_path).expanduser()
        self.timeout = timeout
        self._conn: Optional[sqlite3.Connection] = None

    def init(self) -> None:
        """Initialize the schema (idempotent)."""
        init_kg(self.db_path)
        # Open a persistent connection for performance
        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.timeout,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("KgStore not initialized. Call init() first.")
        return self._conn

    def schema_version(self) -> Optional[str]:
        return get_meta(self.db_path, "schema_version")

    # ============================================================
    # Node operations
    # ============================================================

    def upsert_node(self, node: Node) -> Node:
        """Insert or update a node by id. Idempotent."""
        node.updated_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO nodes (id, type, name, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                name = excluded.name,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (
                node.id, node.type, node.name,
                json.dumps(node.metadata), node.created_at, node.updated_at,
            ),
        )
        self.conn.commit()
        return node

    def upsert_nodes(self, nodes: list[Node]) -> int:
        """Bulk upsert. Returns count upserted."""
        if not nodes:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                n.id, n.type, n.name,
                json.dumps(n.metadata), n.created_at or now, n.updated_at or now,
            )
            for n in nodes
        ]
        self.conn.executemany(
            """
            INSERT INTO nodes (id, type, name, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                name = excluded.name,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def get_node(self, node_id: str) -> Optional[Node]:
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not row:
            return None
        return _row_to_node(row)

    def find_nodes(
        self,
        type: Optional[str] = None,
        name_pattern: Optional[str] = None,
        limit: int = 100,
    ) -> list[Node]:
        """Find nodes by type and/or name pattern."""
        sql = "SELECT * FROM nodes WHERE 1=1"
        params = []
        if type:
            sql += " AND type = ?"
            params.append(type)
        if name_pattern:
            sql += " AND name LIKE ?"
            params.append(f"%{name_pattern}%")
        sql += " ORDER BY name LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_node(r) for r in rows]

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and all its edges (CASCADE)."""
        cur = self.conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ============================================================
    # Edge operations
    # ============================================================

    def upsert_edge(self, edge: Edge) -> Edge:
        """Insert or update an edge. Idempotent (UNIQUE on source+target+type)."""
        self.conn.execute(
            """
            INSERT INTO edges (id, source_id, target_id, type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, type) DO UPDATE SET
                metadata = excluded.metadata
            """,
            (
                edge.id, edge.source_id, edge.target_id, edge.type,
                json.dumps(edge.metadata), edge.created_at,
            ),
        )
        self.conn.commit()
        return edge

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        row = self.conn.execute(
            "SELECT * FROM edges WHERE id = ?", (edge_id,)
        ).fetchone()
        if not row:
            return None
        return _row_to_edge(row)

    def find_edges(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        edge_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[Edge]:
        sql = "SELECT * FROM edges WHERE 1=1"
        params = []
        if source_id:
            sql += " AND source_id = ?"
            params.append(source_id)
        if target_id:
            sql += " AND target_id = ?"
            params.append(target_id)
        if edge_type:
            sql += " AND type = ?"
            params.append(edge_type)
        sql += " LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_edge(r) for r in rows]

    def delete_edge(self, edge_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM edges WHERE id = ?", (edge_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ============================================================
    # Statistics
    # ============================================================

    def count_nodes(self, type: Optional[str] = None) -> int:
        if type:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE type = ?", (type,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return row[0]

    def count_edges(self, edge_type: Optional[str] = None) -> int:
        if edge_type:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM edges WHERE type = ?", (edge_type,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return row[0]

    def stats(self) -> dict:
        """Return KG statistics."""
        return {
            "schema_version": self.schema_version(),
            "total_nodes": self.count_nodes(),
            "total_edges": self.count_edges(),
            "by_node_type": {
                t: self.count_nodes(type=t) for t in [
                    "Component", "Debt", "Decision", "Fix", "Convention", "ADR"
                ]
            },
            "by_edge_type": {
                t: self.count_edges(edge_type=t) for t in [
                    "causes", "resolves", "conflicts", "supersedes",
                    "affects", "blocks", "documents",
                ]
            },
        }


# ============================================================
# Helpers
# ============================================================

def _row_to_node(row: sqlite3.Row) -> Node:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return Node(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        metadata=metadata or {},
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


def _row_to_edge(row: sqlite3.Row) -> Edge:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return Edge(
        id=row["id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        type=row["type"],
        metadata=metadata or {},
        created_at=row["created_at"] or "",
    )
