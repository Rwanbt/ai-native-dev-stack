import sys
import tempfile
import unittest

from ainative_workplane.convergence import converge
from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.runner import RunnerError, VerificationRunner, load_registry
from ainative_workplane.traceability import analyze
from ainative_workplane.trust import evaluate_trust


class RunnerConvergenceTests(unittest.TestCase):
    def binding(self, registry):
        digest = "a" * 64
        reference = lambda prefix: {"uid": generate_uid(prefix), "digest": digest}
        return {
            "work": reference("work"), "contract_revision": 1,
            "contract_digest": digest, "verification_specification": reference("verify"),
            "command_registry_digest": canonical_digest(registry), "policy_digest": digest,
            "approval_root": reference("root"), "repository_snapshot": reference("snapshot"),
            "producer": "test", "producer_version": "1", "evidence_provenance": "LOCAL_UNTRUSTED",
        }

    def test_runner_uses_argv_timeout_and_substance(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"], "timeout_seconds": 3, "max_output_bytes": 100}}}
        with tempfile.TemporaryDirectory() as directory:
            result = VerificationRunner(registry, runs_dir=directory).run("check", cwd=directory, binding=self.binding(registry), require_substance=True)
            self.assertEqual("PASS", result.result)
            self.assertTrue(list(__import__("pathlib").Path(directory).glob("*.json")))
        with self.assertRaisesRegex(RunnerError, "SHELL_COMMAND_FORBIDDEN"):
            load_registry({"schema_name": "command_registry", "schema_version": 1, "commands": {"bad": {"argv": ["echo"], "shell": True}}})

    def test_runner_marks_timeout_and_rejects_registry_drift(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"slow": {"argv": [sys.executable, "-c", "import time; time.sleep(2)"], "timeout_seconds": 1, "max_output_bytes": 100}}}
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual("TIMEOUT", VerificationRunner(registry).run("slow", cwd=directory, binding=self.binding(registry)).result)
        with self.assertRaisesRegex(RunnerError, "COMMAND_REGISTRY_CHANGED"):
            load_registry(registry, expected_digest="b" * 64)
        binding = self.binding(registry)
        binding["command_registry_digest"] = "b" * 64
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RunnerError, "COMMAND_REGISTRY_BINDING_MISMATCH"):
                VerificationRunner(registry).run("slow", cwd=directory, binding=binding)

    def test_runner_rejects_output_exceeding_configured_limit(self):
        registry = {
            "schema_name": "command_registry",
            "schema_version": 1,
            "commands": {
                "noisy": {
                    "argv": [sys.executable, "-c", "print('x' * 101)"],
                    "timeout_seconds": 3,
                    "max_output_bytes": 100,
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RunnerError, "OUTPUT_LIMIT_EXCEEDED"):
                VerificationRunner(registry).run("noisy", cwd=directory, binding=self.binding(registry))

    def test_convergence_ignores_narrative_and_blocks_failures(self):
        graph = analyze([], [], [], [])
        self.assertEqual("INVALID", converge(graph, []).verdict)
        graph = analyze([], [], [], [])
        forged = converge(graph, [{"uid": "run-1", "status": "PASS"}])
        self.assertEqual("BLOCKED", forged.verdict)
        self.assertIn("INVALID_VERIFICATION_EVIDENCE", [gap.code for gap in forged.gaps])
        self.assertEqual("BLOCKED", converge(graph, [{"uid": "run-1", "status": "PASS"}], freshness=["POLICY_CHANGED"]).verdict)

    def test_missing_root_fails_closed(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"]}}}
        with tempfile.TemporaryDirectory() as directory:
            evidence = VerificationRunner(registry).run("check", cwd=directory, binding=self.binding(registry))
        self.assertEqual("ROOT_OF_TRUST_INVALID", evaluate_trust(evidence, policy=None, approval_root=None).code)
