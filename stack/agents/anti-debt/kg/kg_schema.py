"""
kg_schema.py — Schema and dataclasses for the Knowledge Graph (Layer 0).

Per ADR-0023 (Storage V2) and ADR-0017 (Architecture).
Implements SQLite schema + Python dataclasses + JSON serialization.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ============================================================
# Schema version (per ADR-0022)
# ============================================================

KG_SCHEMA_VERSION = "1.0.0"


# ============================================================
# Node types
# ============================================================

NODE_TYPES = {"Component", "Debt", "Decision", "Fix", "Convention", "ADR"}


# ============================================================
# Edge types
# ============================================================

EDGE_TYPES = {
    "causes",       # source causes target
    "resolves",     # source resolves target (typically Fix resolves Debt)
    "conflicts",    # source conflicts with target
    "supersedes",   # source replaces target (typically for ADRs)
    "affects",      # source affects target (typically Debt affects Component)
    "blocks",       # source blocks target (typically Component blocks Decision)
    "documents",    # source documents target (typically ADR documents Decision)
}


# ============================================================
# SQL Schema
# ============================================================

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS _migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS _meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('Component', 'Debt', 'Decision', 'Fix', 'Convention', 'ADR')),
    name TEXT NOT NULL,
    metadata JSON,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('causes', 'resolves', 'conflicts', 'supersedes', 'affects', 'blocks', 'documents')),
    metadata JSON,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE,
    UNIQUE (source_id, target_id, type)
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
"""


# ============================================================
# Dataclasses
# ============================================================

@dataclass
class Node:
    """A node in the knowledge graph."""
    type: str
    name: str
    id: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.type not in NODE_TYPES:
            raise ValueError(f"Invalid node type: {self.type}. Must be one of {NODE_TYPES}")
        if not self.name:
            raise ValueError("Node name is required")
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(
            id=d["id"],
            type=d["type"],
            name=d["name"],
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class Edge:
    """A typed edge between two nodes."""
    source_id: str
    target_id: str
    type: str
    id: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.type not in EDGE_TYPES:
            raise ValueError(f"Invalid edge type: {self.type}. Must be one of {EDGE_TYPES}")
        if self.source_id == self.target_id:
            raise ValueError("Self-loops are not allowed (source_id == target_id)")
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(
            id=d["id"],
            source_id=d["source_id"],
            target_id=d["target_id"],
            type=d["type"],
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", ""),
        )


# ============================================================
# Schema initialization
# ============================================================

def init_kg(kg_db_path: Path) -> None:
    """Initialize a SQLite KG database. Idempotent."""
    kg_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(kg_db_path))
    try:
        conn.executescript(SCHEMA_SQL)
        # Record the current schema version
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('schema_version', ?)",
            (KG_SCHEMA_VERSION,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('initialized_at', ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()


def get_meta(kg_db_path: Path, key: str) -> Optional[str]:
    """Read a meta key from the KG."""
    conn = sqlite3.connect(str(kg_db_path))
    try:
        row = conn.execute("SELECT value FROM _meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ============================================================
# Migration runner (per ADR-0022)
# ============================================================

MIGRATIONS: list = []
"""Registry of (version, callable) tuples. Each callable receives the conn and applies its migration."""


def register_migration(version: str, description: str):
    """Decorator to register a migration."""
    def decorator(fn):
        MIGRATIONS.append({"version": version, "description": description, "up": fn})
        return fn
    return decorator


def run_migrations(kg_db_path: Path, target_version: str = KG_SCHEMA_VERSION) -> list[str]:
    """Run pending migrations to bring KG to target_version.

    Idempotent: re-running is a no-op.
    Returns the list of applied versions.
    """
    init_kg(kg_db_path)  # ensures _migrations table exists
    conn = sqlite3.connect(str(kg_db_path))
    applied = []
    try:
        existing = {row[0] for row in conn.execute("SELECT version FROM _migrations").fetchall()}
        # Sort migrations by version (lexicographic is fine for now)
        sorted_migrations = sorted(MIGRATIONS, key=lambda m: m["version"])
        for mig in sorted_migrations:
            if mig["version"] in existing:
                continue
            if mig["version"] > target_version:
                continue
            mig["up"](conn)
            conn.execute(
                "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
                (mig["version"], datetime.now(timezone.utc).isoformat()),
            )
            applied.append(mig["version"])
        conn.commit()
    finally:
        conn.close()
    return applied
