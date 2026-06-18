"""
kg_sync.py — Bidirectional sync between Knowledge Graph (SQLite) and Vault Obsidian.

Per ADR-0023 (Storage V2) — the Vault is a "projection" of the KG,
optimized for human readability and RAG queries.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kg_schema import Node, Edge
from kg_store import KgStore


# ============================================================
# Vault directory structure (per ADR-0023)
# ============================================================

VAULT_SUBDIRS = {
    "snapshots": "AntiDebt/snapshots",
    "decisions": "AntiDebt/decisions",
    "registry": "AntiDebt/registry",
    "logs": "AntiDebt/logs",
    "dashboards": "AntiDebt/dashboards",
}


def ensure_vault_structure(vault_path: Path) -> dict[str, Path]:
    """Create the AntiDebt/ directory tree in the vault. Returns paths."""
    paths = {}
    for name, subdir in VAULT_SUBDIRS.items():
        p = vault_path / subdir
        p.mkdir(parents=True, exist_ok=True)
        paths[name] = p
    return paths


# ============================================================
# KG → Vault (snapshot projection)
# ============================================================

def kg_to_snapshot(store: KgStore) -> dict:
    """Generate a snapshot of the KG state for vault projection."""
    stats = store.stats()
    return {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": stats["schema_version"],
        "stats": stats,
        "nodes_by_type": {
            t: [
                {"id": n.id, "name": n.name, "metadata": n.metadata}
                for n in store.find_nodes(type=t, limit=10000)
            ]
            for t in ["Component", "Debt", "Decision", "Fix", "Convention", "ADR"]
        },
    }


def render_snapshot_markdown(snapshot: dict) -> str:
    """Render a snapshot as a markdown file for the vault."""
    lines: list[str] = []
    lines.append("---")
    lines.append(f"kg_snapshot: {snapshot['snapshot_at']}")
    lines.append(f"schema_version: {snapshot.get('schema_version', 'unknown')}")
    stats = snapshot["stats"]
    lines.append(f"total_nodes: {stats['total_nodes']}")
    lines.append(f"total_edges: {stats['total_edges']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# KG Snapshot — {snapshot['snapshot_at']}")
    lines.append("")

    # By type
    lines.append("## By type")
    for t, count in stats["by_node_type"].items():
        lines.append(f"- {t}: {count}")
    lines.append("")

    # By edge type
    lines.append("## By edge type")
    for t, count in stats["by_edge_type"].items():
        lines.append(f"- {t}: {count}")
    lines.append("")

    # Open debts (most actionable for humans)
    debts = snapshot["nodes_by_type"].get("Debt", [])
    open_debts = [d for d in debts if d.get("metadata", {}).get("status") in (None, "open", "accepted")]
    if open_debts:
        _sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        lines.append("## Open debts")
        for d in sorted(open_debts,
                        key=lambda x: _sev_order.get(x.get("metadata", {}).get("severity", "low"), 3)):
            sev = d.get("metadata", {}).get("severity", "?")
            lines.append(f"- [{sev}] {d['name']}")
        lines.append("")

    return "\n".join(lines)


def push_snapshot_to_vault(store: KgStore, vault_path: Path) -> Optional[Path]:
    """Generate a snapshot and write it to the vault.

    Returns the path of the written file, or None if vault unavailable.
    """
    if not vault_path.exists():
        return None
    try:
        paths = ensure_vault_structure(vault_path)
        snapshot = kg_to_snapshot(store)
        markdown = render_snapshot_markdown(snapshot)
        stamp = snapshot["snapshot_at"].replace(":", "-")
        out_path = paths["snapshots"] / f"kg-snapshot-{stamp}.md"
        out_path.write_text(markdown, encoding="utf-8")
        return out_path
    except (OSError, PermissionError):
        return None


# ============================================================
# Vault → KG (import from markdown notes)
# ============================================================

def import_adr_from_vault(adr_path: Path, store: KgStore) -> Optional[Node]:
    """Import an ADR markdown file into the KG as an ADR node.

    Expected format (per docs/adr/00NN-title.md convention):
    ```
    # ADR-NNNN — Title
    Status: Proposed | Accepted | Deprecated
    Date: YYYY-MM-DD

    ## Context
    ...
    ## Decision
    ...
    ```
    """
    if not adr_path.exists():
        return None
    try:
        text = adr_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Parse status (best-effort)
    status = "Proposed"
    for line in text.splitlines():
        if line.lower().startswith("status:"):
            status = line.split(":", 1)[1].strip()
            break

    # Derive name from first heading
    name = adr_path.stem  # fallback
    for line in text.splitlines():
        if line.startswith("# "):
            name = line.lstrip("# ").strip()
            break

    # Derive id from path: adr-0023-storage-architecture-v2 → ADR-0023
    node_id = f"adr-{adr_path.stem.split('-')[0]}"

    node = Node(
        id=node_id,
        type="ADR",
        name=name,
        metadata={
            "source": str(adr_path),
            "status": status,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    store.upsert_node(node)
    return node


def import_adrs_from_vault(vault_path: Path, store: KgStore) -> int:
    """Import all ADRs from the vault into the KG. Returns count imported."""
    if not vault_path.exists():
        return 0
    count = 0
    # Look in docs/adr/ first (canonical location)
    canonical = vault_path / "AntiDebt" / "decisions"
    for d in canonical.glob("*.md"):
        if import_adr_from_vault(d, store):
            count += 1
    return count


# ============================================================
# Full sync orchestration
# ============================================================

def full_sync(store: KgStore, vault_path: Path) -> dict:
    """Run a full KG ↔ Vault sync.

    Returns a report of what was synced.
    """
    report = {
        "snapshot_written": None,
        "adrs_imported": 0,
        "errors": [],
    }
    try:
        snap = push_snapshot_to_vault(store, vault_path)
        if snap:
            report["snapshot_written"] = str(snap)
    except Exception as e:
        report["errors"].append(f"snapshot: {e}")

    try:
        report["adrs_imported"] = import_adrs_from_vault(vault_path, store)
    except Exception as e:
        report["errors"].append(f"adr_import: {e}")

    return report
