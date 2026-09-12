"""The complexity checker follows conventions.json, not a copied constant (#39).

conventions.json is declared as the machine-readable source of the size and
complexity rules. A checker carrying its own `BLOCKING = 25` is a third
declaration that can silently drift: the day the policy moves the threshold,
CI keeps enforcing the old number. These tests prove the checker reads the
canonical value and observes a change in it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_complexity_budget.py"

_spec = importlib.util.spec_from_file_location("check_complexity_budget", SCRIPT)
checker = importlib.util.module_from_spec(_spec)
sys.modules["check_complexity_budget"] = checker
_spec.loader.exec_module(checker)


def _write_conventions(root: Path, blocking) -> None:
    (root / "conventions.json").write_text(json.dumps({
        "cyclomatic_complexity": {"target": 10, "alert": 15, "blocking": blocking}}),
        encoding="utf-8")


def _write_function(path: Path, branches: int) -> None:
    body = "\n".join(f"    if flag_{index}:\n        pass" for index in range(branches))
    path.write_text(f"def measured(flag_0=True):\n{body}\n", encoding="utf-8")


class TheBudgetComesFromConventionsJson(unittest.TestCase):

    def test_the_repository_budget_matches_conventions_json(self):
        declared = json.loads((REPO / "conventions.json").read_text(encoding="utf-8"))
        self.assertEqual(checker.read_blocking_budget(REPO),
                         declared["cyclomatic_complexity"]["blocking"])

    def test_a_threshold_change_in_the_canonical_file_is_observed(self):
        with tempfile.TemporaryDirectory(prefix="budget-") as staging:
            root = Path(staging)
            _write_conventions(root, 5)
            self.assertEqual(checker.read_blocking_budget(root), 5)
            _write_conventions(root, 30)
            self.assertEqual(checker.read_blocking_budget(root), 30,
                             "the checker kept an old or hardcoded threshold")

    def test_a_missing_or_invalid_budget_refuses_not_defaults(self):
        with tempfile.TemporaryDirectory(prefix="budget-") as staging:
            root = Path(staging)
            with self.assertRaises(checker.ConventionBudgetMissing):
                checker.read_blocking_budget(root)
            (root / "conventions.json").write_text(
                '{"cyclomatic_complexity": {}}', encoding="utf-8")
            with self.assertRaises(checker.ConventionBudgetMissing):
                checker.read_blocking_budget(root)
            _write_conventions(root, True)
            with self.assertRaises(checker.ConventionBudgetMissing):
                checker.read_blocking_budget(root)

    def test_the_declared_budget_is_the_enforced_boundary(self):
        with tempfile.TemporaryDirectory(prefix="budget-") as staging:
            package = Path(staging)
            _write_function(package / "mod.py", branches=4)   # complexity 5
            findings, counted = checker.measure(package, blocking=3)
            self.assertEqual(counted, 1)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["function"], "measured")
            self.assertEqual(findings[0]["complexity"], 5)
            findings, _ = checker.measure(package, blocking=5)
            self.assertEqual(findings, [], "the declared budget was not the boundary used")


if __name__ == "__main__":
    unittest.main()