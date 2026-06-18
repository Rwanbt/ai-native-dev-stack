#!/usr/bin/env python3
"""Test runner for Layer 1 (static_analysis) and Layer 2 (critic_v2)."""
import sys
import unittest
import json
import tempfile
import os
from pathlib import Path

# Add the tools dir to path (same workaround as the other test runners)
TOOLS = Path(r"D:\App\ai-native-dev-stack\stack\agents\anti-debt\tools")
sys.path.insert(0, str(TOOLS))

import static_analysis  # noqa: E402
import critic_v2  # noqa: E402


class TestStaticAnalysis(unittest.TestCase):
    def test_cc_simple_function(self):
        """A function with no branches should have CC=1."""
        src = "def f():\n    return 1\n"
        tree = ast_mod().parse(src)
        func = tree.body[0]
        cc = static_analysis._cyclomatic_complexity(func)
        self.assertEqual(cc, 1)

    def test_cc_with_branches(self):
        src = (
            "def f(x):\n"
            "    if x:\n"
            "        return 1\n"
            "    elif x > 5:\n"
            "        return 2\n"
            "    else:\n"
            "        return 3\n"
        )
        tree = ast_mod().parse(src)
        func = tree.body[0]
        cc = static_analysis._cyclomatic_complexity(func)
        # 1 base + 2 if/elif = 3
        self.assertEqual(cc, 3)

    def test_cc_boolop(self):
        src = "def f(a,b,c):\n    return a and b and c\n"
        tree = ast_mod().parse(src)
        func = tree.body[0]
        cc = static_analysis._cyclomatic_complexity(func)
        # 1 + 2 (and has 3 values -> 2 extra)
        self.assertEqual(cc, 3)

    def test_max_nesting(self):
        src = (
            "def f():\n"
            "    for i in range(10):\n"
            "        if i > 5:\n"
            "            while i:\n"
            "                i -= 1\n"
        )
        tree = ast_mod().parse(src)
        func = tree.body[0]
        nesting = static_analysis._max_nesting(func)
        # for > if > while = 3
        self.assertEqual(nesting, 3)

    def test_function_signature(self):
        src = "def f(a, b, *args, c, **kwargs): pass\n"
        tree = ast_mod().parse(src)
        func = tree.body[0]
        sig = static_analysis._function_signature(func)
        self.assertIn("a", sig)
        self.assertIn("*args", sig)
        self.assertIn("**kwargs", sig)

    def test_ast_hash_stable(self):
        # Two functions with identical bodies but different names must share the
        # same ast_hash. Exercises the REAL production hashing path
        # (analyze_file), not a helper that nothing else calls.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "dup.py"
            p.write_text("def f():\n    return 1\n\n\ndef g():\n    return 1\n")
            _findings, records = static_analysis.analyze_file(p)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["ast_hash"], records[1]["ast_hash"])

    def test_analyze_file_finds_complexity(self):
        # Create a synthetic file with a complex function
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "complex.py"
            p.write_text(
                "def very_complex(x):\n"
                "    if x > 0:\n        return 1\n"
                "    elif x > 5:\n        return 2\n"
                "    elif x > 10:\n        return 3\n"
                "    elif x > 15:\n        return 4\n"
                "    elif x > 20:\n        return 5\n"
                "    elif x > 25:\n        return 6\n"
                "    elif x > 30:\n        return 7\n"
                "    elif x > 35:\n        return 8\n"
                "    elif x > 40:\n        return 9\n"
                "    elif x > 45:\n        return 10\n"
                "    elif x > 50:\n        return 11\n"
                "    else:\n        return 0\n"
            )
            findings, records = static_analysis.analyze_file(p)
            self.assertTrue(len(findings) > 0, "should find complexity issue")
            self.assertTrue(any(f["subcategory"] == "complexity" for f in findings))

    def test_analyze_repo_finds_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("def f():\n    return 1\n")
            (root / "b.py").write_text("def g():\n    if True:\n        return 1\n    return 2\n")
            result = static_analysis.analyze_repo(root)
            self.assertEqual(result["stats"]["files_scanned"], 2)
            self.assertGreaterEqual(result["stats"]["functions_analyzed"], 2)


class TestCriticV2(unittest.TestCase):
    def _finding(self, conf=0.9, sev="medium", effort="M", risk="medium"):
        return {
            "id": "f-" + str(conf),
            "category": "code",
            "subcategory": "test",
            "severity": sev,
            "location": {"file": "x.py", "lines": "1"},
            "description": "test",
            "evidence": [],
            "confidence": conf,
            "source": "tool:test",
            "estimated_effort": effort,
            "risk_of_fix": risk,
        }

    def test_tier_reject(self):
        f = self._finding(conf=0.2)
        self.assertEqual(critic_v2.tier(f), "reject")

    def test_tier_review(self):
        f = self._finding(conf=0.65)  # 0.6 <= c < 0.7 -> review
        self.assertEqual(critic_v2.tier(f), "review")

    def test_tier_reject_below_floor(self):
        # 0.5 is below the 0.6 non-negotiable reject floor (was 'review' under
        # the old 0.4 floor — locked here to prevent silent regression).
        f = self._finding(conf=0.5)
        self.assertEqual(critic_v2.tier(f), "reject")

    def test_tier_accept(self):
        f = self._finding(conf=0.95)
        self.assertEqual(critic_v2.tier(f), "accept")

    def test_score_critical_high(self):
        f = self._finding(conf=1.0, sev="critical", effort="S", risk="low")
        s = critic_v2.compute_score(f)
        # impact 4, urgency 4 (default = impact), conf 1.0, effort 0.25 * 1.0 = 0.25
        # score = 4*4*1.0 / 0.25 = 64
        self.assertEqual(s, 64.0)

    def test_score_low(self):
        f = self._finding(conf=1.0, sev="low", effort="XL", risk="high")
        s = critic_v2.compute_score(f)
        # impact 1, urgency 1, conf 1.0, effort 10 * 2.5 = 25
        # score = 1 / 25 = 0.04
        self.assertLess(s, 1.0)

    def test_score_monotonic_severity(self):
        low = critic_v2.compute_score(self._finding(conf=0.9, sev="low"))
        med = critic_v2.compute_score(self._finding(conf=0.9, sev="medium"))
        high = critic_v2.compute_score(self._finding(conf=0.9, sev="high"))
        crit = critic_v2.compute_score(self._finding(conf=0.9, sev="critical"))
        self.assertLess(low, med)
        self.assertLess(med, high)
        self.assertLess(high, crit)

    def test_score_effort_inverse(self):
        s_small = critic_v2.compute_score(self._finding(effort="XS"))
        s_large = critic_v2.compute_score(self._finding(effort="XL"))
        self.assertGreater(s_small, s_large)

    def test_triage_buckets(self):
        findings = [self._finding(conf=c) for c in [0.2, 0.5, 0.9, 0.95, 0.1, 0.65, 0.3]]
        triaged = critic_v2.triage(findings)
        self.assertEqual(len(triaged["rejected"]), 4)  # 0.2, 0.5, 0.1, 0.3 (all < 0.6)
        self.assertEqual(len(triaged["review"]), 1)    # 0.65 (0.6 <= c < 0.7)
        self.assertEqual(len(triaged["accepted"]), 2)  # 0.9, 0.95

    def test_build_triage_has_critic_validation(self):
        findings = [self._finding(conf=0.9, sev="high")]
        triage = critic_v2.build_triage(findings, project="test-proj")
        self.assertIn("triage_id", triage)
        self.assertIn("critic_validation", triage)
        self.assertEqual(triage["critic_validation"]["engine_version"], "v2.0.0")
        self.assertEqual(triage["project"], "test-proj")
        self.assertEqual(len(triage["fix_order"]), 1)
        self.assertEqual(triage["fix_order"][0]["tier"], "accept")
        self.assertIn("score", triage["fix_order"][0])

    def test_override_record_valid(self):
        h = critic_v2.load_history(Path("/nonexistent/file.json"))
        entry = critic_v2.record_override(h, "f-001", "accept_override", "valid reason here")
        self.assertEqual(entry["finding_id"], "f-001")
        self.assertEqual(len(h["overrides"]), 1)

    def test_override_record_too_short_reason(self):
        h = critic_v2.load_history(Path("/nonexistent/file.json"))
        with self.assertRaises(ValueError):
            critic_v2.record_override(h, "f-001", "accept_override", "short")

    def test_override_record_invalid_action(self):
        h = critic_v2.load_history(Path("/nonexistent/file.json"))
        with self.assertRaises(ValueError):
            critic_v2.record_override(h, "f-001", "garbage", "valid reason here")

    def test_calibration_kill_switch(self):
        h = {
            "overrides": [{"action": "accept_override", "finding_id": "f1"}] * 5,
            "resolutions": [{"finding_id": f"r{i}"} for i in range(10)],
        }
        stats = critic_v2.compute_calibration_stats(h)
        # 5 overrides / 10 resolutions = 0.5 > 0.30 threshold
        self.assertTrue(stats["kill_switch_triggered"])
        self.assertEqual(stats["override_rate"], 0.5)

    def test_calibration_no_kill_switch_low_rate(self):
        h = {
            "overrides": [{"action": "accept_override", "finding_id": "f1"}] * 2,
            "resolutions": [{"finding_id": f"r{i}"} for i in range(10)],
        }
        stats = critic_v2.compute_calibration_stats(h)
        # 2/10 = 0.2 < 0.30
        self.assertFalse(stats["kill_switch_triggered"])

    def test_calibration_no_resolutions(self):
        h = {"overrides": [], "resolutions": []}
        stats = critic_v2.compute_calibration_stats(h)
        self.assertEqual(stats["override_rate"], 0.0)
        self.assertFalse(stats["kill_switch_triggered"])


def ast_mod():
    import ast
    return ast


def hashlib_mod():
    import hashlib
    return hashlib


if __name__ == "__main__":
    unittest.main(verbosity=2)
