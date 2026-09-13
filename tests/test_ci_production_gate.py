"""The Production Gate: the one required check on main, and why it cannot be vacuous.

GitHub only blocks a merge on checks the branch protection names. Before this
gate, a hundred suites ran and four were required, so a regression in any of the
others reported green on a PR. The gate is a single aggregate job whose needs
are every blocking job; these tests pin three facts: the gate covers exactly the
blocking jobs the workflow defines (a newly added job cannot silently stay out,
and a removed one cannot linger), a job that failed, was cancelled or was
skipped unexpectedly fails the gate, and a job missing from the payload fails
too — absence is not success.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

STACK = Path(__file__).resolve().parents[1]
WORKFLOW = STACK / ".github" / "workflows" / "ci.yml"

# Jobs that intentionally do not block a merge:
#   production-gate    — the gate itself, not a dependency of itself;
#   test-legacy-python — Python 3.8 is best-effort by documented contract.
EXEMPT_JOBS = frozenset({"production-gate", "test-legacy-python"})


def _job_ids(text: str) -> list[str]:
    jobs_at = text.index("\njobs:\n")
    body = text[jobs_at + len("\njobs:\n"):]
    return re.findall(r"^  ([a-z0-9][a-z0-9-]*):$", body, re.M)


def _job_block(text: str, job: str) -> str:
    start = text.index(f"\n  {job}:\n")
    rest = text[start + 1:]
    match = re.search(r"^  [a-z0-9][a-z0-9-]*:$", rest[len(f"  {job}:\n"):], re.M)
    return rest if match is None else rest[: len(f"  {job}:\n") + match.start()]


class ProductionGateWorkflow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.jobs = _job_ids(cls.text)
        cls.block = _job_block(cls.text, "production-gate")

    def test_the_gate_exists_and_always_runs(self):
        self.assertIn("production-gate", self.jobs)
        self.assertIn("if: always()", self.block)

    def test_the_gate_needs_every_blocking_job_and_no_other(self):
        needs_match = re.search(r"needs: \[([^\]]+)\]", self.block)
        self.assertIsNotNone(needs_match, "production-gate must declare its needs")
        needs = [item.strip() for item in needs_match.group(1).split(",")]
        expected_line = re.search(r"PRODUCTION_GATE_EXPECTED: (.+)", self.block)
        self.assertIsNotNone(expected_line, "the gate must pass its expected list")
        expected = expected_line.group(1).split()

        blocking = [job for job in self.jobs if job not in EXEMPT_JOBS]
        self.assertEqual(sorted(needs), sorted(expected),
                         "needs and PRODUCTION_GATE_EXPECTED must agree")
        self.assertEqual(sorted(needs), sorted(blocking),
                         "every blocking job must be in the gate, and only those")
        for job in needs:
            self.assertIn(job, self.jobs, f"the gate needs an unknown job: {job}")

    def test_legacy_python_is_best_effort_and_outside_the_gate(self):
        legacy = _job_block(self.text, "test-legacy-python")
        self.assertIn("continue-on-error: true", legacy)
        self.assertIn('"3.8"', legacy)
        self.assertNotIn("test-legacy-python", self.block)


class ProductionGateLogic(unittest.TestCase):

    def test_all_success_passes(self):
        from scripts.ci_production_gate import evaluate
        payload = {"a": {"result": "success"}, "b": {"result": "success"}}
        ok, problems = evaluate(payload, ["a", "b"])
        self.assertTrue(ok, problems)

    def test_failure_cancelled_and_skipped_all_fail_the_gate(self):
        from scripts.ci_production_gate import evaluate
        for result in ("failure", "cancelled", "skipped", "neutral", None):
            payload = {"a": {"result": "success"}, "b": {"result": result}}
            ok, problems = evaluate(payload, ["a", "b"])
            self.assertFalse(ok, f"{result} must fail the gate")
            self.assertIn("b", problems[0])

    def test_a_missing_job_fails_the_gate(self):
        from scripts.ci_production_gate import evaluate
        ok, problems = evaluate({"a": {"result": "success"}}, ["a", "b"])
        self.assertFalse(ok)
        self.assertIn("missing", problems[0])

    def test_the_script_exits_0_1_2_with_stable_meanings(self):
        script = STACK / "scripts" / "ci_production_gate.py"
        base = {**os.environ, "PYTHONIOENCODING": "utf-8"}

        ok = subprocess.run(
            [sys.executable, str(script)],
            env={**base, "PRODUCTION_GATE_NEEDS": json.dumps({"a": {"result": "success"}}),
                 "PRODUCTION_GATE_EXPECTED": "a"},
            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)

        bad = subprocess.run(
            [sys.executable, str(script)],
            env={**base, "PRODUCTION_GATE_NEEDS": json.dumps({"a": {"result": "cancelled"}}),
                 "PRODUCTION_GATE_EXPECTED": "a"},
            capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("cancelled", bad.stderr)

        missing_env = subprocess.run([sys.executable, str(script)], env=base,
                                     capture_output=True, text=True)
        self.assertEqual(missing_env.returncode, 2)

        broken = subprocess.run(
            [sys.executable, str(script)],
            env={**base, "PRODUCTION_GATE_NEEDS": "{not json",
                 "PRODUCTION_GATE_EXPECTED": "a"},
            capture_output=True, text=True)
        self.assertEqual(broken.returncode, 2)


if __name__ == "__main__":
    unittest.main()
