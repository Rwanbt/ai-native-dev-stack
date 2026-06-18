"""
kg_migrate.py — Migration script V1 (JSON files) → V2 (SQLite KG).

Per ADR-0019 (Migration V1 → V2), this is Phase 1 (dual-write setup).
Reads existing V1 JSON files and creates corresponding KG nodes.

V1 file conventions:
  .debt-scan.json     → Component + Debt nodes
  .debt-history.json  → temporal edges (scans_at, resolved_at, regressed_at)
  .debt-plan.json     → Decision nodes
  .fix-<id>.patch     → Fix nodes
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kg_schema import Node, Edge
from kg_store import KgStore
from kg_sync import full_sync


def _stable_hash(s: str) -> str:
    """Deterministic 8-hex digest. Unlike builtin hash() on str, this is NOT
    salted by PYTHONHASHSEED, so ids are identical across separate processes —
    required for idempotent re-migration."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


# ============================================================
# V1 file readers
# ============================================================

def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


# ============================================================
# V1 → V2 conversion
# ============================================================

def finding_to_debt_node(finding: dict) -> Node:
    """Convert a V1 finding to a V2 Debt node."""
    return Node(
        id=finding.get("id", f"debt-v1-{_stable_hash(finding.get('description', ''))}"),
        type="Debt",
        name=finding.get("description", "Unknown debt")[:200],
        metadata={
            "category": finding.get("category"),
            "subcategory": finding.get("subcategory"),
            "severity": finding.get("severity"),
            "source": finding.get("source"),
            "confidence": finding.get("confidence"),
            "location": finding.get("location", {}),
            "estimated_effort": finding.get("estimated_effort"),
            "risk_of_fix": finding.get("risk_of_fix"),
            "auto_fixable": finding.get("auto_fixable", False),
            "status": "open",  # all V1 findings are open by default
            "v1_imported": True,
        },
    )


def file_to_component_node(file_path: str) -> Node:
    """Convert a file path to a Component node."""
    return Node(
        id=f"comp-{_stable_hash(file_path)}",
        type="Component",
        name=file_path,
        metadata={"kind": "source_file", "v1_imported": True},
    )


def scan_to_event_edges(scan: dict, scan_id: Optional[str] = None) -> list[Edge]:
    """Convert a V1 scan to temporal event edges."""
    edges: list[Edge] = []
    if scan_id is None:
        scan_id = scan.get("scan_id", f"scan-v1-{datetime.now().timestamp()}")
    scan_at = scan.get("timestamp", datetime.now(timezone.utc).isoformat())

    for finding in scan.get("findings", []):
        debt_id = finding.get("id")
        if not debt_id:
            continue
        # Edge: scan -> debt (created_at)
        edges.append(Edge(
            id=f"edge-{scan_id}-{debt_id}-created",
            source_id=scan_id,
            target_id=debt_id,
            type="causes",
            metadata={"event": "detected", "scan_at": scan_at},
        ))
        # If finding has a file location, link to component
        file_path = finding.get("location", {}).get("file")
        if file_path:
            comp_id = f"comp-{_stable_hash(file_path)}"
            edges.append(Edge(
                id=f"edge-{debt_id}-{comp_id}-affects",
                source_id=debt_id,
                target_id=comp_id,
                type="affects",
                metadata={"scan_at": scan_at},
            ))
    return edges


def history_to_resolved_edges(history: dict) -> tuple[list[Node], list[Edge]]:
    """Convert V1 history to (fix_nodes, edges).

    Each resolved finding gets a synthetic Fix node + a 'resolves' edge.
    """
    edges: list[Edge] = []
    fix_nodes: list[Node] = []
    for scan in history.get("scans", []):
        scan_id = scan.get("scan_id", "")
        scan_at = scan.get("timestamp", "")
        for resolved_id in scan.get("findings_resolved", []):
            # Synthetic fix_id deterministic from inputs (idempotent)
            fix_id = f"fix-v1-{resolved_id}-{scan_id}"
            # Create a corresponding Fix node (deterministic id)
            fix_node = Node(
                id=fix_id,
                type="Fix",
                name=f"V1 historical fix for {resolved_id}",
                metadata={
                    "v1_synthetic": True,
                    "source_scan": scan_id,
                    "resolved_at": scan_at,
                },
            )
            fix_nodes.append(fix_node)
            edges.append(Edge(
                id=f"edge-{fix_id}-{resolved_id}-resolves",
                source_id=fix_id,
                target_id=resolved_id,
                type="resolves",
                metadata={"scan_at": scan_at, "v1_imported": True},
            ))
    return fix_nodes, edges


def plan_to_decision_node(plan: dict) -> Node:
    """Convert a V1 plan to a Decision node."""
    return Node(
        id=plan.get("plan_id", f"plan-v1-{datetime.now().timestamp()}"),
        type="Decision",
        name=f"Plan {plan.get('plan_id', '?')}",
        metadata={
            "mode": plan.get("mode"),
            "scan_id": plan.get("scan_id"),
            "actions_count": len(plan.get("actions", [])),
            "accepted_debt_count": len(plan.get("accepted_debt", [])),
            "v1_imported": True,
        },
    )


# ============================================================
# Migration orchestrator
# ============================================================

def _process_scan_file(store: KgStore, scan_path: Path, report: dict) -> None:
    """Import one V1 .debt-scan.json: Scan node + Debt/Component nodes + edges."""
    scan = _read_json(scan_path)
    if not scan:
        report["errors"].append(f"unreadable: {scan_path}")
        return
    try:
        v1_scan_id = scan.get("scan_id")
        # Deterministic id from V1 scan_id (or path) -> idempotent
        scan_node_id = (f"scan-v1-{v1_scan_id}" if v1_scan_id
                        else f"scan-v1-path-{_stable_hash(str(scan_path))}")
        scan_node = Node(
            id=scan_node_id, type="Decision",  # a scan is a decision-making event
            name=f"Scan {v1_scan_id or scan_path.stem}",
            metadata={"kind": "scan", "scan_at": scan.get("timestamp", ""), "v1_imported": True},
        )
        store.upsert_node(scan_node)

        findings = scan.get("findings", [])
        store.upsert_nodes([finding_to_debt_node(f) for f in findings])
        report["debts_created"] += len(findings)

        # Component nodes (deduplicated by file path)
        comp_ids, comp_nodes = set(), []
        for f in findings:
            fp = f.get("location", {}).get("file")
            if fp and fp not in comp_ids:
                comp_ids.add(fp)
                comp_nodes.append(file_to_component_node(fp))
        store.upsert_nodes(comp_nodes)
        report["components_created"] += len(comp_nodes)

        edges = scan_to_event_edges(scan, scan_id=scan_node.id)
        for e in edges:
            store.upsert_edge(e)
        report["edges_created"] += len(edges)
        report["scans_processed"] += 1
    except Exception as e:
        report["errors"].append(f"scan {scan_path}: {e}")


def _process_history_file(store: KgStore, hist_path: Path, report: dict) -> None:
    """Import one V1 .debt-history.json: synthetic Fix nodes + 'resolves' edges."""
    history = _read_json(hist_path)
    if not history:
        return
    try:
        fix_nodes, edges = history_to_resolved_edges(history)
        store.upsert_nodes(fix_nodes)
        for e in edges:
            store.upsert_edge(e)
        report["edges_created"] += len(edges)
    except Exception as e:
        report["errors"].append(f"history {hist_path}: {e}")


def _process_plan_file(store: KgStore, plan_path: Path, report: dict) -> None:
    """Import one V1 .debt-plan.json as a Decision node (idempotent id)."""
    plan = _read_json(plan_path)
    if not plan:
        return
    # Guard against shape confusion: a DebtTriage (fix_order, no actions) is NOT
    # a DebtPlan. Importing it would silently record actions_count=0.
    if "fix_order" in plan and "actions" not in plan:
        report["errors"].append(
            f"plan {plan_path}: looks like a DebtTriage (has 'fix_order', no 'actions') "
            f"— expected a DebtPlan. Skipped (see debt-triage.schema.json).")
        return
    try:
        decision = plan_to_decision_node(plan)
        v1_plan_id = plan.get("plan_id")
        if v1_plan_id:
            decision.id = f"decision-v1-{v1_plan_id}"
        store.upsert_node(decision)
        report["decisions_created"] += 1
        report["plans_processed"] += 1
    except Exception as e:
        report["errors"].append(f"plan {plan_path}: {e}")


def migrate_v1_to_v2(
    v1_root: Path,
    kg_db: Path,
    vault_path: Optional[Path] = None,
) -> dict:
    """Migrate V1 JSON files to V2 SQLite KG. Idempotent (UPSERT). Returns a report."""
    report = {
        "v1_root": str(v1_root), "kg_db": str(kg_db),
        "components_created": 0, "debts_created": 0, "decisions_created": 0,
        "edges_created": 0, "scans_processed": 0, "plans_processed": 0, "errors": [],
    }
    with KgStore(kg_db) as store:
        for scan_path in v1_root.rglob(".debt-scan.json"):
            _process_scan_file(store, scan_path, report)
        for hist_path in v1_root.rglob(".debt-history.json"):
            _process_history_file(store, hist_path, report)
        for plan_path in v1_root.rglob(".debt-plan.json"):
            _process_plan_file(store, plan_path, report)
        if vault_path and vault_path.exists():
            try:
                report["vault_sync"] = full_sync(store, vault_path)
            except Exception as e:
                report["errors"].append(f"vault_sync: {e}")
    return report
