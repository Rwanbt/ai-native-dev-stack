#!/usr/bin/env python3
"""Test runner for Layer 4 (scan_periodic), Layer 6 (calibration), Layer 7 (dashboard)."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(r"D:\App\ai-native-dev-stack\stack\agents\anti-debt\tools")
sys.path.insert(0, str(TOOLS))

import scan_periodic  # noqa: E402
import calibration  # noqa: E402
import dashboard  # noqa: E402


class TestScanPeriodic(unittest.TestCase):
    def test_format_alert_empty(self):
        self.assertEqual(scan_periodic._format_alert("proj", []), "")

    def test_format_alert_critical(self):
        findings = [{"severity": "critical", "subcategory": "secrets",
                      "description": "API key leaked in config.py"}]
        msg = scan_periodic._format_alert("myproject", findings)
        self.assertIn("myproject", msg)
        self.assertIn("secrets", msg)
        self.assertIn("API key leaked", msg)

    def test_format_alert_mixed(self):
        findings = [
            {"severity": "critical", "subcategory": "x", "description": "crit1"},
            {"severity": "high", "subcategory": "y", "description": "high1"},
            {"severity": "low", "subcategory": "z", "description": "low1"},
        ]
        msg = scan_periodic._format_alert("p", findings)
        self.assertIn("1 critical", msg)
        self.assertIn("1 high", msg)
        # low findings are not alerted
        self.assertNotIn("z", msg)

    def test_alert_log_writes_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "alerts.log"
            scan_periodic._alert_log("test message", log_path)
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("test message", content)
            self.assertIn("T", content)  # timestamp contains T separator

    def test_alert_telegram_no_env(self):
        # Without env vars, should return False (no crash)
        result = scan_periodic._alert_telegram("test")
        self.assertFalse(result)

    def test_alert_log_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "alerts.log"
            scan_periodic._alert_log("first", log_path)
            scan_periodic._alert_log("second", log_path)
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("first", content)
            self.assertIn("second", content)
            self.assertEqual(content.count("["), 2)  # 2 timestamps


class TestCalibration(unittest.TestCase):
    def _history(self, overrides: list, resolutions: list = None) -> dict:
        return {"overrides": overrides, "resolutions": resolutions or []}

    def test_empty_history(self):
        bucket = calibration.analyze_overrides({"overrides": []})
        self.assertEqual(bucket, {})

    def test_bucket_classification(self):
        h = self._history([
            {"action": "confirm", "original_confidence": 0.2},
            {"action": "confirm", "original_confidence": 0.5},
            {"action": "confirm", "original_confidence": 0.8},
            {"action": "confirm", "original_confidence": 0.95},
        ])
        b = calibration.analyze_overrides(h)
        self.assertEqual(b["0.0-0.4"]["total"], 1)
        self.assertEqual(b["0.4-0.7"]["total"], 1)
        self.assertEqual(b["0.7-0.9"]["total"], 1)
        self.assertEqual(b["0.9-1.0"]["total"], 1)

    def test_precision_proxy(self):
        h = self._history([
            {"action": "confirm", "original_confidence": 0.95},
            {"action": "confirm", "original_confidence": 0.95},
            {"action": "reject_override", "original_confidence": 0.95},
        ])
        b = calibration.analyze_overrides(h)
        # 2 confirmed + 1 reject_override => 2/3 = 0.67
        self.assertAlmostEqual(b["0.9-1.0"]["precision_proxy"], 2/3, places=2)

    def test_propose_no_change_when_well_calibrated(self):
        # All confirms, no reject_overrides, high precision everywhere
        h = self._history([
            {"action": "confirm", "original_confidence": c} for c in [0.1, 0.5, 0.8, 0.95]
        ] * 10)
        b = calibration.analyze_overrides(h)
        proposal = calibration.propose_thresholds(b)
        self.assertEqual(proposal["reject_below"], calibration.DEFAULT_REJECT)
        self.assertEqual(proposal["review_below"], calibration.DEFAULT_REVIEW)

    def test_propose_lower_reject_when_low_bucket_poor(self):
        h = self._history([
            {"action": "reject_override", "original_confidence": 0.3}
        ] * 10)
        b = calibration.analyze_overrides(h)
        proposal = calibration.propose_thresholds(b)
        # precision_proxy = 0/10 = 0.0 < 0.9, so reject threshold should drop
        self.assertLess(proposal["reject_below"], calibration.DEFAULT_REJECT)

    def test_propose_raises_warning_for_high_bucket(self):
        h = self._history([
            {"action": "reject_override", "original_confidence": 0.95}
        ] * 10)
        b = calibration.analyze_overrides(h)
        proposal = calibration.propose_thresholds(b)
        # Should mention a warning about high-bucket
        joined = " ".join(proposal["rationale"])
        self.assertIn("WARNING", joined)

    def test_generate_report_contains_sections(self):
        h = self._history([{"action": "confirm", "original_confidence": 0.5}])
        b = calibration.analyze_overrides(h)
        p = calibration.propose_thresholds(b)
        with tempfile.TemporaryDirectory() as tmp:
            hist_path = Path(tmp) / "history.json"
            hist_path.write_text(json.dumps(h))
            report = calibration.generate_report(hist_path, b, p)
        self.assertIn("# Anti-Debt Calibration Report", report)
        self.assertIn("Precision by confidence bucket", report)
        self.assertIn("Current vs proposed thresholds", report)

    def test_main_no_history(self):
        # Calling main without args should fail (argparse requires history)
        with self.assertRaises(SystemExit):
            calibration.main()


class TestDashboard(unittest.TestCase):
    def test_render_html_basic(self):
        from collections import Counter
        stats = {
            "total_nodes": 10, "total_edges": 8,
            "by_node_type": {"Component": 1, "Debt": 9},
            "by_edge_type": {"affects": 8},
            "components": [{"name": "test-proj", "metadata": '{"path": "/tmp/test"}'}],
            "debts": [
                {"severity": "critical", "category": "security", "subcategory": "secrets",
                 "file": "config.py", "line": "9", "first_seen": "2026-06-17T10:00:00Z",
                 "name": "Hardcoded secret"},
                {"severity": "high", "category": "code", "subcategory": "complexity",
                 "file": "main.py", "line": "100", "first_seen": "2026-06-17T11:00:00Z",
                 "name": "Function too complex"},
            ],
            "by_severity": Counter({"critical": 1, "high": 1, "medium": 0, "low": 0}),
            "by_category": Counter({"security": 1, "code": 1}),
            "top_files": [("config.py", 1), ("main.py", 1)],
            "recent_debts": [
                {"id": "d1", "name": "Hardcoded secret",
                 "metadata": '{"severity": "critical", "category": "security", "subcategory": "secrets", "file": "config.py", "line": "9", "first_seen": "2026-06-17T10:00:00Z"}'},
            ],
        }
        html = dashboard.render_html(stats)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("test-proj", html)
        self.assertIn("Hardcoded secret", html)
        self.assertIn("config.py", html)
        self.assertIn("CRITICAL", html)

    def test_load_stats_no_db(self):
        # Use a non-existent path - load_stats should raise sqlite error
        with self.assertRaises(sqlite3.OperationalError):
            dashboard.load_stats(Path("Z:/nonexistent/path.db"))

    def test_severity_colors_present(self):
        self.assertIn("critical", dashboard.SEVERITY_COLORS)
        self.assertIn("high", dashboard.SEVERITY_COLORS)
        self.assertEqual(dashboard.SEVERITY_COLORS["critical"], "#dc2626")


if __name__ == "__main__":
    unittest.main(verbosity=2)
