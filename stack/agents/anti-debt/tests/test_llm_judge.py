#!/usr/bin/env python3
"""Tests for llm_judge.py — structural validation (no API calls needed)."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import llm_judge


class TestRubric(unittest.TestCase):
    def test_rubric_has_four_criteria(self):
        self.assertEqual(len(llm_judge.RUBRIC), 4)
        expected = {"faithfulness", "actionability", "severity_accuracy", "evidence_quality"}
        self.assertEqual(set(llm_judge.RUBRIC.keys()), expected)

    def test_each_criterion_has_grades(self):
        for name, criterion in llm_judge.RUBRIC.items():
            self.assertIn("question", criterion)
            self.assertIn("grades", criterion)
            self.assertEqual(set(criterion["grades"].keys()), {"good", "fair", "poor"})


class TestPromptBuilding(unittest.TestCase):
    def test_build_prompt_without_source(self):
        finding = {"id": "test-1", "description": "test finding", "severity": "high"}
        prompt = llm_judge.build_judge_prompt(finding, source_code=None)
        self.assertIn("test-1", prompt)
        self.assertIn("faithfulness", prompt)
        self.assertIn("actionability", prompt)
        self.assertNotIn("Source code referenced", prompt)

    def test_build_prompt_with_source(self):
        finding = {"id": "test-2", "description": "complexity issue"}
        prompt = llm_judge.build_judge_prompt(finding, source_code="def foo():\n    pass")
        self.assertIn("Source code referenced", prompt)
        self.assertIn("def foo()", prompt)

    def test_source_code_truncated_at_4000(self):
        finding = {"id": "test-3"}
        long_source = "x" * 10000
        prompt = llm_judge.build_judge_prompt(finding, source_code=long_source)
        self.assertLessEqual(len(prompt), 20000)


class TestJudgeFinding(unittest.TestCase):
    def test_skipped_without_api_key(self):
        finding = {"id": "no-key", "description": "test"}
        with patch.dict("os.environ", {}, clear=True):
            result = llm_judge.judge_finding(finding)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["finding_id"], "no-key")

    def test_valid_api_response_parsed(self):
        mock_response = {
            "grades": {
                "faithfulness": "good",
                "actionability": "fair",
                "severity_accuracy": "good",
                "evidence_quality": "good",
            },
            "rationale": "Mostly solid finding",
        }
        finding = {"id": "mock-1", "description": "test"}
        with patch("llm_judge.call_judge_api", return_value=mock_response):
            result = llm_judge.judge_finding(finding)
        self.assertEqual(result["status"], "evaluated")
        self.assertTrue(result["pass"])
        self.assertEqual(result["grades"]["actionability"], "fair")

    def test_poor_grade_means_fail(self):
        mock_response = {
            "grades": {
                "faithfulness": "poor",
                "actionability": "good",
                "severity_accuracy": "good",
                "evidence_quality": "good",
            },
            "rationale": "Fabricated description",
        }
        finding = {"id": "mock-2", "description": "test"}
        with patch("llm_judge.call_judge_api", return_value=mock_response):
            result = llm_judge.judge_finding(finding)
        self.assertFalse(result["pass"])

    def test_invalid_grades_default_to_poor(self):
        mock_response = {
            "grades": {
                "faithfulness": "excellent",
                "actionability": "good",
                "severity_accuracy": "good",
                "evidence_quality": "good",
            },
            "rationale": "test",
        }
        finding = {"id": "mock-3"}
        with patch("llm_judge.call_judge_api", return_value=mock_response):
            result = llm_judge.judge_finding(finding)
        self.assertEqual(result["grades"]["faithfulness"], "poor")
        self.assertFalse(result["pass"])


class TestSummary(unittest.TestCase):
    def test_compute_summary_empty(self):
        summary = llm_judge._compute_summary([])
        self.assertEqual(summary["pass_rate"], 0.0)

    def test_compute_summary_all_pass(self):
        results = [
            {"status": "evaluated", "pass": True, "grades": {
                "faithfulness": "good", "actionability": "good",
                "severity_accuracy": "good", "evidence_quality": "good"}},
            {"status": "evaluated", "pass": True, "grades": {
                "faithfulness": "fair", "actionability": "good",
                "severity_accuracy": "good", "evidence_quality": "fair"}},
        ]
        summary = llm_judge._compute_summary(results)
        self.assertEqual(summary["pass_rate"], 1.0)
        self.assertEqual(summary["total_evaluated"], 2)

    def test_compute_summary_mixed(self):
        results = [
            {"status": "evaluated", "pass": True, "grades": {
                "faithfulness": "good", "actionability": "good",
                "severity_accuracy": "good", "evidence_quality": "good"}},
            {"status": "evaluated", "pass": False, "grades": {
                "faithfulness": "poor", "actionability": "good",
                "severity_accuracy": "good", "evidence_quality": "good"}},
            {"status": "skipped", "finding_id": "x"},
        ]
        summary = llm_judge._compute_summary(results)
        self.assertEqual(summary["pass_rate"], 0.5)
        self.assertEqual(summary["by_criterion"]["faithfulness"]["poor"], 1)


class TestReport(unittest.TestCase):
    def test_report_generates_markdown(self):
        results = {
            "metadata": {"evaluated_at": "2026-06-21", "source_file": "test.json",
                         "total_findings": 2, "total_evaluated": 2, "total_skipped": 0},
            "results": [
                {"finding_id": "a", "status": "evaluated", "pass": True,
                 "grades": {"faithfulness": "good", "actionability": "good",
                            "severity_accuracy": "good", "evidence_quality": "good"},
                 "rationale": "solid"},
                {"finding_id": "b", "status": "evaluated", "pass": False,
                 "grades": {"faithfulness": "poor", "actionability": "good",
                            "severity_accuracy": "good", "evidence_quality": "good"},
                 "rationale": "fabricated"},
            ],
            "summary": {"pass_rate": 0.5, "total_evaluated": 2,
                        "by_criterion": {
                            "faithfulness": {"good": 1, "fair": 0, "poor": 1, "pass_rate": 0.5},
                            "actionability": {"good": 2, "fair": 0, "poor": 0, "pass_rate": 1.0},
                            "severity_accuracy": {"good": 2, "fair": 0, "poor": 0, "pass_rate": 1.0},
                            "evidence_quality": {"good": 2, "fair": 0, "poor": 0, "pass_rate": 1.0},
                        }},
        }
        report = llm_judge.judge_report(results)
        self.assertIn("# LLM-as-Judge Evaluation Report", report)
        self.assertIn("50.0%", report)
        self.assertIn("**b**", report)
        self.assertIn("fabricated", report)


if __name__ == "__main__":
    unittest.main()
