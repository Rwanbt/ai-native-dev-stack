#!/usr/bin/env python3
"""
registry.py — CRUD on the Debt Registry.

Per ADR-0017 (Layer 3) and V-max design Layer 4 (Governance Skills).
Persists to the KG (Layer 0) and syncs to the vault (V2 only).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Allow import from kg/ directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "kg"))

from kg_schema import Node, Edge
from kg_store import KgStore
from kg_sync import push_snapshot_to_vault

# Canonical KG location — shared with scan_periodic.py so the governance layer
# (registry) and the detection layer (scanners) read/write the SAME database.
DEFAULT_KG_DB = Path(__file__).resolve().parent.parent.parent.parent / "kg" / "data" / "kg.db"


# Debt Registry schema
DEBT_REGISTRY_SCHEMA = {
    "type": "object",
    "required": ["debts"],
    "properties": {
        "debts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["debt_id", "status", "updated_at"],
                "properties": {
                    "debt_id": {"type": "string"},
                    "status": {"enum": ["open", "in_progress", "accepted", "resolved"]},
                    "owner": {"type": "string"},
                    "due_date": {"type": "string", "format": "date"},
                    "accepted_reason": {"type": "string", "minLength": 50},
                    "fix_id": {"type": "string"},
                },
            },
        },
    },
}


def cmd_register(args) -> int:
    """Register a new debt in the registry (or update existing)."""
    if not args.reason or len(args.reason) < 50:
        print(json.dumps({"error": "reason must be at least 50 chars"}))
        return 1

    with KgStore(args.kg_db) as store:
        # Find the debt node (or create one)
        debt = store.get_node(args.debt_id)
        if not debt:
            debt = Node(
                type="Debt",
                name=args.name or f"Debt {args.debt_id}",
                metadata={"severity": args.severity or "medium"},
            )
        else:
            debt.type = "Debt"  # ensure type

        # Update metadata
        debt.metadata["status"] = "accepted"
        debt.metadata["accepted_reason"] = args.reason
        if args.owner:
            debt.metadata["owner"] = args.owner
        if args.due_date:
            debt.metadata["due_date"] = args.due_date
        debt.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        store.upsert_node(debt)

        # Sync to vault
        snap = push_snapshot_to_vault(store, args.vault) if args.vault else None

        print(json.dumps({
            "operation": "register",
            "debt_id": debt.id,
            "status": debt.metadata.get("status"),
            "vault_snapshot": str(snap) if snap else None,
        }, indent=2))
    return 0


def cmd_update_status(args) -> int:
    """Update the status of an existing debt."""
    valid = ["open", "in_progress", "accepted", "resolved"]
    if args.new_status not in valid:
        print(json.dumps({"error": f"status must be one of {valid}"}))
        return 1

    with KgStore(args.kg_db) as store:
        debt = store.get_node(args.debt_id)
        if not debt:
            print(json.dumps({"error": f"debt not found: {args.debt_id}"}))
            return 1

        debt.metadata["status"] = args.new_status
        debt.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        if args.reason:
            debt.metadata[f"status_change_{args.new_status}_reason"] = args.reason
        store.upsert_node(debt)

        if args.vault:
            push_snapshot_to_vault(store, args.vault)

        print(json.dumps({
            "operation": "update_status",
            "debt_id": debt.id,
            "new_status": args.new_status,
        }, indent=2))
    return 0


def cmd_query(args) -> int:
    """Query debts with filters."""
    with KgStore(args.kg_db) as store:
        debts = store.find_nodes(type="Debt", limit=10000)
        results = []
        for d in debts:
            md = d.metadata or {}
            if args.status and md.get("status") != args.status:
                continue
            if args.owner and md.get("owner") != args.owner:
                continue
            if args.severity and md.get("severity") != args.severity:
                continue
            results.append({
                "id": d.id,
                "name": d.name,
                "status": md.get("status"),
                "owner": md.get("owner"),
                "due_date": md.get("due_date"),
                "severity": md.get("severity"),
                "accepted_reason": md.get("accepted_reason"),
            })

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        results.sort(key=lambda r: severity_order.get(r.get("severity") or "low", 3))

        print(json.dumps({
            "operation": "query",
            "count": len(results),
            "debts": results,
        }, indent=2))
    return 0


def cmd_assign(args) -> int:
    """Assign an owner to a debt."""
    if not args.owner:
        print(json.dumps({"error": "owner is required"}))
        return 1

    with KgStore(args.kg_db) as store:
        debt = store.get_node(args.debt_id)
        if not debt:
            print(json.dumps({"error": f"debt not found: {args.debt_id}"}))
            return 1

        debt.metadata["owner"] = args.owner
        debt.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        store.upsert_node(debt)

        print(json.dumps({
            "operation": "assign",
            "debt_id": debt.id,
            "owner": args.owner,
        }, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Debt Registry CRUD")
    parser.add_argument("--kg-db", type=Path, default=DEFAULT_KG_DB)
    parser.add_argument("--vault", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # register
    p_reg = subparsers.add_parser("register")
    p_reg.add_argument("--debt-id", required=True)
    p_reg.add_argument("--name", default=None)
    p_reg.add_argument("--severity", choices=["critical", "high", "medium", "low"])
    p_reg.add_argument("--owner", default=None)
    p_reg.add_argument("--due-date", default=None)
    p_reg.add_argument("--reason", required=True)
    p_reg.set_defaults(func=cmd_register)

    # update-status
    p_us = subparsers.add_parser("update-status")
    p_us.add_argument("--debt-id", required=True)
    p_us.add_argument("--new-status", required=True)
    p_us.add_argument("--reason", default=None)
    p_us.set_defaults(func=cmd_update_status)

    # query
    p_q = subparsers.add_parser("query")
    p_q.add_argument("--status", default=None)
    p_q.add_argument("--owner", default=None)
    p_q.add_argument("--severity", default=None)
    p_q.set_defaults(func=cmd_query)

    # assign
    p_a = subparsers.add_parser("assign")
    p_a.add_argument("--debt-id", required=True)
    p_a.add_argument("--owner", required=True)
    p_a.set_defaults(func=cmd_assign)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
