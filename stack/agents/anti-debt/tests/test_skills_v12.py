"""
tests/test_skills_v12.py — Tests for the V1.2 skills (debt-architecture, debt-prevention, debt-manage).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Allow imports via direct paths (avoid namespace package issues)
ANTI_DEBT = Path(__file__).parent.parent
sys.path.insert(0, str(ANTI_DEBT / "kg"))
sys.path.insert(0, str(ANTI_DEBT / "skills" / "debt-architecture" / "tools"))
sys.path.insert(0, str(ANTI_DEBT / "skills" / "debt-prevention" / "tools"))
sys.path.insert(0, str(ANTI_DEBT / "skills" / "debt-manage" / "tools"))

from scan_architecture import (
    detect_circular_imports_repo,
    detect_high_coupling_python,
    cycles_to_findings,
    coupling_to_findings,
)
from prevent_finding import (
    aggregate_patterns,
    generate_rule,
    generate_regression_test,
    RULE_TEMPLATES,
)
from registry import (
    cmd_register, cmd_update_status, cmd_query, cmd_assign,
    DEBT_REGISTRY_SCHEMA,
)
from kg_schema import Node, init_kg
from kg_store import KgStore


class TestArchitectureScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_circular_in_clean_repo(self):
        (self.repo / "a.py").write_text("from b import x\n")
        (self.repo / "b.py").write_text("# no imports\n")
        cycles = detect_circular_imports_repo(self.repo)
        self.assertEqual(len(cycles), 0)

    def test_detects_circular_import(self):
        (self.repo / "a.py").write_text("from b import x\n")
        (self.repo / "b.py").write_text("from a import y\n")
        cycles = detect_circular_imports_repo(self.repo)
        self.assertGreater(len(cycles), 0)

    def test_finds_high_coupling(self):
        imports = "\n".join([f"import mod{i}" for i in range(15)])
        (self.repo / "god.py").write_text(imports + "\n")
        for i in range(15):
            (self.repo / f"mod{i}.py").write_text("x = 1\n")
        coupling = detect_high_coupling_python(self.repo, threshold=10)
        self.assertEqual(len(coupling), 1)
        self.assertEqual(coupling[0]["count"], 15)

    def test_cycles_to_findings(self):
        cycles = [["a", "b", "a"]]
        findings = cycles_to_findings(cycles, self.repo)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["category"], "architecture")
        self.assertEqual(findings[0]["subcategory"], "circular_dependency")


class TestPreventionGenerator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_aggregate_patterns_threshold(self):
        findings = [
            {"category": "code", "subcategory": "complexity", "id": f"f{i}"}
            for i in range(5)
        ] + [
            {"category": "code", "subcategory": "duplication", "id": "g1"},
        ]
        patterns = aggregate_patterns(findings, threshold=3)
        self.assertEqual(len(patterns), 1)
        self.assertIn(("code", "complexity"), patterns)

    def test_generate_rule_python_complexity(self):
        finding = {"category": "code", "subcategory": "complexity"}
        path = generate_rule(finding, language="python", out_dir=self.out_dir)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("mccabe", content)

    def test_generate_rule_unknown_pattern(self):
        finding = {"category": "unknown", "subcategory": "unknown"}
        path = generate_rule(finding, language="python", out_dir=self.out_dir)
        self.assertIsNone(path)

    def test_generate_regression_test(self):
        pattern_key = ("code", "complexity")
        findings = [{"description": "function too complex"}]
        path = generate_regression_test(pattern_key, findings, self.out_dir)
        self.assertTrue(path.exists())

    def test_rule_templates_have_required_fields(self):
        for key, tpl in RULE_TEMPLATES.items():
            self.assertIn("tool", tpl)
            self.assertIn("config_path", tpl)
            self.assertIn("config", tpl)


class TestDebtManage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "kg.db"
        self.kg = KgStore(self.db)
        self.kg.init()
        self.debt = Node(
            type="Debt",
            name="API key committed",
            metadata={"severity": "critical", "status": "open"},
        )
        self.kg.upsert_node(self.debt)

    def tearDown(self):
        self.kg.close()
        self.tmp.cleanup()

    def test_register_with_short_reason_fails(self):
        args = type('Args', (), {
            'kg_db': self.db, 'vault': None, 'debt_id': 'new-1',
            'name': 'test', 'severity': 'low', 'owner': None,
            'due_date': None, 'reason': 'short', 'command': 'register',
        })()
        result = cmd_register(args)
        self.assertNotEqual(result, 0)

    def test_register_accepted(self):
        args = type('Args', (), {
            'kg_db': self.db, 'vault': None, 'debt_id': self.debt.id,
            'name': None, 'severity': None, 'owner': 'erwan',
            'due_date': '2027-01-01',
            'reason': 'Known debt, will be fixed in V2 of the project, low priority',
            'command': 'register',
        })()
        result = cmd_register(args)
        self.assertEqual(result, 0)
        with KgStore(self.db) as store:
            updated = store.get_node(self.debt.id)
            self.assertEqual(updated.metadata["status"], "accepted")
            self.assertEqual(updated.metadata["owner"], "erwan")

    def test_update_status(self):
        args = type('Args', (), {
            'kg_db': self.db, 'vault': None, 'debt_id': self.debt.id,
            'new_status': 'in_progress', 'reason': None, 'command': 'update-status',
        })()
        result = cmd_update_status(args)
        self.assertEqual(result, 0)

    def test_query(self):
        args = type('Args', (), {
            'kg_db': self.db, 'vault': None, 'status': 'open',
            'owner': None, 'severity': None, 'command': 'query',
        })()
        result = cmd_query(args)
        self.assertEqual(result, 0)

    def test_assign(self):
        args = type('Args', (), {
            'kg_db': self.db, 'vault': None, 'debt_id': self.debt.id,
            'owner': 'erwan', 'command': 'assign',
        })()
        result = cmd_assign(args)
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
