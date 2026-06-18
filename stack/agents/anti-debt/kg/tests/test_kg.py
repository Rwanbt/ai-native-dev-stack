"""
tests/test_kg.py — Unit tests for the Knowledge Graph (Layer 0).

Covers: schema, store CRUD, query, sync, migration.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

# Allow test to import the kg module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from kg_schema import (
    Node, Edge, init_kg, KG_SCHEMA_VERSION, NODE_TYPES, EDGE_TYPES,
)
from kg_store import KgStore
from kg_query import KgQuery
from kg_sync import (
    kg_to_snapshot, render_snapshot_markdown, full_sync,
    ensure_vault_structure, VAULT_SUBDIRS,
)
from kg_migrate import (
    migrate_v1_to_v2, finding_to_debt_node, file_to_component_node,
    plan_to_decision_node, scan_to_event_edges, history_to_resolved_edges,
)


class TestSchema(unittest.TestCase):
    def test_node_validation(self):
        with self.assertRaises(ValueError):
            Node(type="Invalid", name="x")
        with self.assertRaises(ValueError):
            Node(type="Component", name="")
        n = Node(type="Component", name="processAudio")
        self.assertTrue(n.id)
        self.assertTrue(n.created_at)

    def test_edge_validation(self):
        n = Node(type="Component", name="x")
        with self.assertRaises(ValueError):
            Edge(source_id=n.id, target_id=n.id, type="blocks")
        with self.assertRaises(ValueError):
            Edge(source_id=n.id, target_id="other", type="invalid_type")

    def test_node_roundtrip(self):
        n = Node(type="Debt", name="test", metadata={"sev": "high"})
        d = n.to_dict()
        n2 = Node.from_dict(d)
        self.assertEqual(n.id, n2.id)
        self.assertEqual(n.name, n2.name)
        self.assertEqual(n.metadata, n2.metadata)

    def test_edge_roundtrip(self):
        e = Edge(source_id="a", target_id="b", type="causes", metadata={"x": 1})
        d = e.to_dict()
        e2 = Edge.from_dict(d)
        self.assertEqual(e.id, e2.id)
        self.assertEqual(e.metadata, e2.metadata)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "kg.db"
        self.kg = KgStore(self.db)
        self.kg.init()

    def tearDown(self):
        self.kg.close()
        self.tmp.cleanup()

    def test_schema_version(self):
        self.assertEqual(self.kg.schema_version(), KG_SCHEMA_VERSION)

    def test_upsert_node_idempotent(self):
        n = Node(type="Component", name="processAudio", metadata={"x": 1})
        self.kg.upsert_node(n)
        self.kg.upsert_node(n)  # twice
        self.assertEqual(self.kg.count_nodes(), 1)

    def test_bulk_upsert(self):
        nodes = [Node(type="Debt", name=f"d{i}") for i in range(50)]
        n = self.kg.upsert_nodes(nodes)
        self.assertEqual(n, 50)
        self.assertEqual(self.kg.count_nodes(type="Debt"), 50)

    def test_upsert_edge_uniqueness(self):
        n1 = Node(type="Debt", name="d1")
        n2 = Node(type="Fix", name="f1")
        self.kg.upsert_nodes([n1, n2])
        e = Edge(source_id=n2.id, target_id=n1.id, type="resolves")
        self.kg.upsert_edge(e)
        self.kg.upsert_edge(e)  # duplicate
        self.assertEqual(self.kg.count_edges(), 1)

    def test_find_nodes(self):
        self.kg.upsert_node(Node(type="Component", name="processAudio"))
        self.kg.upsert_node(Node(type="Component", name="renderUI"))
        comps = self.kg.find_nodes(type="Component")
        self.assertEqual(len(comps), 2)
        pattern = self.kg.find_nodes(name_pattern="process")
        self.assertEqual(len(pattern), 1)

    def test_delete_node_cascades(self):
        n1 = Node(type="Component", name="a")
        n2 = Node(type="Debt", name="b")
        self.kg.upsert_nodes([n1, n2])
        self.kg.upsert_edge(Edge(source_id=n2.id, target_id=n1.id, type="affects"))
        self.kg.delete_node(n1.id)
        self.assertEqual(self.kg.count_edges(), 0)
        self.assertIsNone(self.kg.get_node(n1.id))

    def test_stats(self):
        self.kg.upsert_node(Node(type="Component", name="c"))
        self.kg.upsert_node(Node(type="Debt", name="d"))
        s = self.kg.stats()
        self.assertEqual(s["total_nodes"], 2)
        self.assertEqual(s["by_node_type"]["Component"], 1)
        self.assertEqual(s["by_node_type"]["Debt"], 1)


class TestQuery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "kg.db"
        self.kg = KgStore(self.db)
        self.kg.init()
        self.q = KgQuery(self.kg)
        # Build a small fixture KG
        self.comp = Node(type="Component", name="processAudio")
        self.debt = Node(type="Debt", name="unused loop variable", metadata={"severity": "high"})
        self.fix = Node(type="Fix", name="remove loop")
        self.kg.upsert_nodes([self.comp, self.debt, self.fix])
        self.kg.upsert_edge(Edge(source_id=self.debt.id, target_id=self.comp.id, type="affects"))
        self.kg.upsert_edge(Edge(source_id=self.fix.id, target_id=self.debt.id, type="resolves"))

    def tearDown(self):
        self.kg.close()
        self.tmp.cleanup()

    def test_find_debts_affecting_component(self):
        debts = self.q.find_debts_affecting_component("processAudio")
        self.assertEqual(len(debts), 1)
        self.assertEqual(debts[0].id, self.debt.id)

    def test_find_fixes_for_debt(self):
        fixes = self.q.find_fixes_for_debt(self.debt.id)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0].id, self.fix.id)

    def test_find_root_causes(self):
        # No 'causes' edges in this fixture, so root cause = self
        chains = self.q.find_root_causes(self.debt.id, max_depth=3)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0][0].id, self.debt.id)

    def test_find_consequences(self):
        # No outgoing 'causes' from debt, so consequence = self
        chains = self.q.find_consequences(self.debt.id, max_depth=3)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0][0].id, self.debt.id)


class TestSync(unittest.TestCase):
    def setUp(self):
        self.kg_tmp = tempfile.TemporaryDirectory()
        self.vault_tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.kg_tmp.name) / "kg.db"
        self.vault = Path(self.vault_tmp.name)
        self.kg = KgStore(self.db)
        self.kg.init()

    def tearDown(self):
        self.kg.close()
        self.kg_tmp.cleanup()
        self.vault_tmp.cleanup()

    def test_ensure_vault_structure(self):
        paths = ensure_vault_structure(self.vault)
        for name in VAULT_SUBDIRS:
            self.assertTrue(paths[name].exists())

    def test_full_sync(self):
        self.kg.upsert_node(Node(type="Component", name="x"))
        self.kg.upsert_node(Node(type="Debt", name="y", metadata={"severity": "high", "status": "open"}))
        report = full_sync(self.kg, self.vault)
        self.assertIsNotNone(report["snapshot_written"])
        self.assertTrue(Path(report["snapshot_written"]).exists())

    def test_snapshot_markdown_renders(self):
        self.kg.upsert_node(Node(type="Component", name="a"))
        snapshot = kg_to_snapshot(self.kg)
        md = render_snapshot_markdown(snapshot)
        self.assertIn("Component", md)
        self.assertIn("total_nodes", md.lower() or "total_nodes" in md)


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.v1_tmp = tempfile.TemporaryDirectory()
        self.kg_tmp = tempfile.TemporaryDirectory()
        self.v1_root = Path(self.v1_tmp.name)
        self.db = Path(self.kg_tmp.name) / "kg.db"

    def tearDown(self):
        self.v1_tmp.cleanup()
        self.kg_tmp.cleanup()

    def test_migrate_empty_repo(self):
        report = migrate_v1_to_v2(self.v1_root, self.db)
        self.assertEqual(report["scans_processed"], 0)
        self.assertEqual(report["plans_processed"], 0)
        # KG should be empty but initialized
        with KgStore(self.db) as store:
            self.assertEqual(store.count_nodes(), 0)

    def test_migrate_one_scan(self):
        # Create a V1 .debt-scan.json
        scan = {
            "scan_id": "scan-1",
            "timestamp": "2026-06-17T10:00:00Z",
            "findings": [
                {
                    "id": "f-001",
                    "category": "security",
                    "subcategory": "secrets_in_code",
                    "severity": "critical",
                    "description": "API key committed",
                    "location": {"file": "src/config.py:12"},
                    "confidence": 0.99,
                    "source": "tool:trufflehog",
                }
            ]
        }
        (self.v1_root / ".debt-scan.json").write_text(json.dumps(scan))

        report = migrate_v1_to_v2(self.v1_root, self.db)
        self.assertEqual(report["scans_processed"], 1)
        self.assertEqual(report["debts_created"], 1)
        self.assertEqual(report["components_created"], 1)
        self.assertGreaterEqual(report["edges_created"], 2)

        # Verify KG state
        with KgStore(self.db) as store:
            self.assertEqual(store.count_nodes(type="Debt"), 1)
            self.assertEqual(store.count_nodes(type="Component"), 1)
            self.assertGreaterEqual(store.count_edges(), 2)

    def test_idempotent(self):
        scan = {"scan_id": "s1", "timestamp": "t1", "findings": []}
        (self.v1_root / ".debt-scan.json").write_text(json.dumps(scan))
        migrate_v1_to_v2(self.v1_root, self.db)
        report2 = migrate_v1_to_v2(self.v1_root, self.db)
        # No findings = nothing to upsert, so 0 created both times
        self.assertEqual(report2["scans_processed"], 1)


class TestIntegration(unittest.TestCase):
    """End-to-end test: V1 files → V2 KG → Vault sync → query."""

    def setUp(self):
        self.v1_tmp = tempfile.TemporaryDirectory()
        self.kg_tmp = tempfile.TemporaryDirectory()
        self.vault_tmp = tempfile.TemporaryDirectory()
        self.v1_root = Path(self.v1_tmp.name)
        self.db = Path(self.kg_tmp.name) / "kg.db"
        self.vault = Path(self.vault_tmp.name)

    def tearDown(self):
        self.v1_tmp.cleanup()
        self.kg_tmp.cleanup()
        self.vault_tmp.cleanup()

    def test_end_to_end(self):
        # 1. Create V1 files
        (self.v1_root / ".debt-scan.json").write_text(json.dumps({
            "scan_id": "s1",
            "findings": [
                {"id": "f-1", "category": "code", "subcategory": "complexity",
                 "severity": "high", "description": "complex function",
                 "location": {"file": "src/foo.py"}, "confidence": 0.9, "source": "tool:ruff"}
            ]
        }))
        # 2. Migrate V1 → V2
        migrate_v1_to_v2(self.v1_root, self.db, vault_path=self.vault)
        # 3. Query the KG
        with KgStore(self.db) as store:
            q = KgQuery(store)
            debts = q.find_debts_affecting_component("src/foo.py")
            self.assertEqual(len(debts), 1)
            # 4. Sync to vault
            snap = full_sync(store, self.vault)
            self.assertIsNotNone(snap["snapshot_written"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
