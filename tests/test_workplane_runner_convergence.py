import sys
import tempfile
import time
import unittest

from ainative_workplane.convergence import converge
from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.runner import RunnerError, VerificationRunner, load_registry
from ainative_workplane.traceability import analyze
from ainative_workplane.trust import approval_root_commitment, evaluate_trust, policy_commitment
from ainative_workplane.freshness import FreshnessResult, evaluate_freshness


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

    def authorization(self, registry):
        placeholder = "a" * 64
        policy = {
            "schema_name": "project_policy", "schema_version": 1,
            "approval_predicate": {"predicate_id": "review", "policy_digest": placeholder},
            "success_condition_mutation_provenance": "GIT_REVIEWED",
            "verification_evidence_provenance": "GIT_REVIEWED",
            "waiver_approval_rule": {"predicate_id": "waiver", "policy_digest": placeholder},
            "human_approval_rule": {"predicate_id": "human", "policy_digest": placeholder},
            "promotion_policy": "explicit",
        }
        digest = policy_commitment(policy)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            policy[field]["policy_digest"] = digest
        root = {
            "schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"),
            "root_digest": placeholder, "policy_digest": digest, "root_provenance": "GIT_REVIEWED",
            "bootstrap": {"initialized_at": "2026-09-02T00:00:00Z", "initialized_by": "test"},
        }
        root["root_digest"] = approval_root_commitment(root)
        binding = self.binding(registry)
        binding.update({"policy_digest": digest, "approval_root": {"uid": root["uid"], "digest": root["root_digest"]}, "evidence_provenance": "GIT_REVIEWED"})
        return policy, root, binding

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

    def test_runner_timeout_terminates_child_process_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = __import__("pathlib").Path(directory) / "child-survived.txt"
            child = "import pathlib,time; time.sleep(2); pathlib.Path(r'%s').write_text('survived')" % str(marker).replace("\\", "\\\\")
            parent = "import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', %r]); time.sleep(5)" % child
            registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"tree": {"argv": [sys.executable, "-c", parent], "timeout_seconds": 1}}}
            result = VerificationRunner(registry).run("tree", cwd=directory, binding=self.binding(registry))
            self.assertEqual("TIMEOUT", result.result)
            time.sleep(2.5)
            self.assertFalse(marker.exists())

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
        missing = converge(graph, [])
        self.assertEqual("NOT_CONVERGED", missing.verdict)
        self.assertIn("NO_MEANINGFUL_REQUIREMENTS", [gap.code for gap in missing.gaps])
        self.assertIn("FRESHNESS_UNAVAILABLE", [gap.code for gap in missing.gaps])
        self.assertIn("NO_VERIFICATION_EVIDENCE", [gap.code for gap in missing.gaps])
        graph = analyze([], [], [], [])
        forged = converge(graph, [{"uid": "run-1", "status": "PASS"}])
        self.assertEqual("NOT_CONVERGED", forged.verdict)
        self.assertIn("INVALID_VERIFICATION_EVIDENCE", [gap.code for gap in forged.gaps])
        self.assertEqual("NOT_CONVERGED", converge(graph, [{"uid": "run-1", "status": "PASS"}], freshness=FreshnessResult(frozenset({"POLICY_CHANGED"}))).verdict)

    def test_missing_root_fails_closed(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"]}}}
        with tempfile.TemporaryDirectory() as directory:
            evidence = VerificationRunner(registry).run("check", cwd=directory, binding=self.binding(registry))
        self.assertEqual("ROOT_OF_TRUST_INVALID", evaluate_trust(evidence, policy=None, approval_root=None).code)

    def test_trust_binds_policy_and_requires_complete_root_chain(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"]}}}
        policy, root, binding = self.authorization(registry)
        with tempfile.TemporaryDirectory() as directory:
            evidence = VerificationRunner(registry).run("check", cwd=directory, binding=binding)
        self.assertEqual("TRUSTED", evaluate_trust(evidence, policy=policy, approval_root=root).code)

        parent = dict(root)
        parent["uid"] = generate_uid("root")
        parent["root_digest"] = approval_root_commitment(parent)
        chained_root = dict(root)
        chained_root["predecessor"] = {"uid": parent["uid"], "digest": parent["root_digest"]}
        chained_root["root_digest"] = approval_root_commitment(chained_root)
        chained_binding = dict(binding)
        chained_binding["approval_root"] = {"uid": chained_root["uid"], "digest": chained_root["root_digest"]}
        with tempfile.TemporaryDirectory() as directory:
            chained_evidence = VerificationRunner(registry).run("check", cwd=directory, binding=chained_binding)
        self.assertEqual("ROOT_OF_TRUST_INVALID", evaluate_trust(chained_evidence, policy=policy, approval_root=chained_root).code)
        self.assertEqual("TRUSTED", evaluate_trust(chained_evidence, policy=policy, approval_root=chained_root, approval_chain=[parent]).code)

        invalid_policy = dict(policy)
        invalid_policy["approval_predicate"] = dict(policy["approval_predicate"])
        invalid_policy["approval_predicate"]["policy_digest"] = "b" * 64
        self.assertEqual("POLICY_COMMITMENT_INVALID", evaluate_trust(evidence, policy=invalid_policy, approval_root=root).code)

    def test_freshness_detects_changed_contract_registry_policy_root_and_snapshot(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"]}}}
        binding = self.binding(registry)
        with tempfile.TemporaryDirectory() as directory:
            evidence = VerificationRunner(registry).run("check", cwd=directory, binding=binding)
        current_snapshot = {"uid": binding["repository_snapshot"]["uid"], "digest": binding["repository_snapshot"]["digest"]}
        fresh = evaluate_freshness(evidence, current_contract_digest=binding["contract_digest"], current_snapshot=current_snapshot, current_registry_digest=binding["command_registry_digest"], current_policy_digest=binding["policy_digest"], current_approval_root=binding["approval_root"])
        self.assertEqual(frozenset(), fresh.states)
        stale = evaluate_freshness(evidence, current_contract_digest="b" * 64, current_snapshot={"uid": "other", "digest": "b" * 64}, current_registry_digest="b" * 64, current_policy_digest="b" * 64, current_approval_root={"uid": "other", "digest": "b" * 64})
        self.assertTrue({"STALE_CONTRACT", "STALE_SCOPE", "COMMAND_REGISTRY_CHANGED", "POLICY_CHANGED", "ROOT_OF_TRUST_CHANGED"}.issubset(stale.states))
