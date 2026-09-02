import sys
import tempfile
import unittest

from ainative_workplane.convergence import converge
from ainative_workplane.runner import RunnerError, VerificationRunner, load_registry
from ainative_workplane.traceability import analyze


class RunnerConvergenceTests(unittest.TestCase):
    def test_runner_uses_argv_timeout_and_substance(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"], "timeout_seconds": 3, "max_output_bytes": 100}}}
        with tempfile.TemporaryDirectory() as directory:
            result = VerificationRunner(registry, runs_dir=directory).run("check", cwd=directory, require_substance=True)
            self.assertEqual("PASS", result.status)
            self.assertTrue(list(__import__("pathlib").Path(directory).glob("*.json")))
        with self.assertRaisesRegex(RunnerError, "SHELL_COMMAND_FORBIDDEN"):
            load_registry({"schema_name": "command_registry", "schema_version": 1, "commands": {"bad": {"argv": ["echo"], "shell": True}}})

    def test_convergence_ignores_narrative_and_blocks_failures(self):
        graph = analyze([], [], [], [])
        self.assertEqual("INVALID", converge(graph, []).verdict)
        graph = analyze([], [], [], [])
        self.assertEqual("BLOCKED", converge(graph, [{"uid": "run-1", "status": "FAIL"}]).verdict)
        self.assertEqual("BLOCKED", converge(graph, [{"uid": "run-1", "status": "PASS"}], freshness=["POLICY_CHANGED"]).verdict)

