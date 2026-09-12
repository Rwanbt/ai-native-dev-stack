"""Classifier: advisory suggestions only, never stored, never state."""
import unittest

from ainative.knowledge.classifier import RULES, suggest


class ClassifierTests(unittest.TestCase):
    def test_keyword_hit_returns_kind_and_reasons(self):
        result = suggest("the suite is flaky on windows")
        self.assertEqual("FAILURE_PATTERN", result["kind"])
        self.assertTrue(result["reasons"])

    def test_unknown_when_nothing_matches(self):
        result = suggest("lorem ipsum dolor sit amet")
        self.assertEqual("UNKNOWN", result["kind"])

    def test_module_hint_adds_module_invariant(self):
        result = suggest("this detail matters", module="planner")
        self.assertEqual("MODULE_INVARIANT", result["kind"])

    def test_deterministic_and_pure(self):
        first = suggest("we decided to prefer the local runtime")
        second = suggest("we decided to prefer the local runtime")
        self.assertEqual(first, second)

    def test_frozen_advisory_table_shape(self):
        self.assertEqual(7, len(RULES))
        kinds = [kind for kind, _words, _reason in RULES]
        self.assertEqual(len(kinds), len(set(kinds)))


if __name__ == "__main__":
    unittest.main()
