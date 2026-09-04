import sys
import tempfile
from datetime import datetime
import time
import unittest

from ainative_workplane.convergence import VERDICT_EXIT_CODES, converge
from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.runner import RunnerError, VerificationRunner, load_registry
from ainative_workplane.traceability import analyze
from ainative_workplane.trust import TrustVerdict, approval_root_commitment, evaluate_trust, policy_commitment, successor_commitment
from ainative_workplane.freshness import FreshnessResult, evaluate_freshness
from ainative_workplane.provenance import ProvenanceFacts

# The kernel is unit-tested with the facts the production path observes for
# itself; nothing here lets a caller supply them to a production verdict.
ESTABLISHED = ProvenanceFacts(git_recorded=True, local_dirty=False)


class RunnerConvergenceTests(unittest.TestCase):
    def binding(self, registry):
        digest = "a" * 64
        reference = lambda prefix: {"uid": generate_uid(prefix), "digest": digest}
        return {
            "work": reference("work"), "contract_revision": 1,
            "contract_digest": digest, "verification_specification": reference("verify"),
            "command_registry_digest": canonical_digest(registry), "policy_digest": digest,
            "approval_root": reference("root"), "repository_snapshot": reference("snapshot"),
            "snapshot_content_digest": digest, "snapshot_dependency_digest": digest,
            "snapshot_head": "0" * 40,
            "producer": "test", "producer_version": "1", "evidence_provenance": "LOCAL_UNTRUSTED",
        }

    def authorization(self, registry):
        placeholder = "a" * 64
        policy = {
            "schema_name": "project_policy", "schema_version": 1,
            "approval_predicate": {"predicate_id": "recorded_owner_ack", "policy_digest": placeholder},
            "required_mutation_facts": {"git_recorded": True},
            "required_evidence_facts": {"git_recorded": True},
            "waiver_approval_rule": {"predicate_id": "recorded_owner_ack", "policy_digest": placeholder},
            "human_approval_rule": {"predicate_id": "recorded_owner_ack", "policy_digest": placeholder},
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
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"], "timeout_seconds": 3, "max_output_bytes": 100, "substance": {"type": "exit_only", "minimum_observations": 0}}}}
        with tempfile.TemporaryDirectory() as directory:
            result = VerificationRunner(registry, runs_dir=directory).run("check", cwd=directory, binding=self.binding(registry), require_substance=True)
            self.assertEqual("PASS", result.result)
            self.assertTrue(list(__import__("pathlib").Path(directory).glob("*.json")))
        with self.assertRaisesRegex(RunnerError, "SHELL_COMMAND_FORBIDDEN"):
            load_registry({"schema_name": "command_registry", "schema_version": 1, "commands": {"bad": {"argv": ["echo"], "shell": True}}})

    def test_recorded_execution_window_spans_the_real_run(self):
        """EMP-002. Both ends were stamped at record-build time, so every run in
        every audit trail claimed to have started and finished at the same
        instant. H01 froze a 5 524 ms run whose window was 35 microseconds."""

        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"slow": {"argv": [sys.executable, "-c", "import time; time.sleep(0.4); print('ok')"], "timeout_seconds": 10, "substance": {"type": "exit_only", "minimum_observations": 0}}}}
        with tempfile.TemporaryDirectory() as directory:
            record = VerificationRunner(registry).run("slow", cwd=directory, binding=self.binding(registry)).to_record()
        started = datetime.fromisoformat(record["started_at"])
        finished = datetime.fromisoformat(record["finished_at"])
        window_ms = (finished - started).total_seconds() * 1000
        self.assertGreaterEqual(window_ms, 300, "the recorded window is shorter than the sleep the command performed")
        self.assertGreaterEqual(window_ms, record["duration_ms"] * 0.5, "the recorded window contradicts the measured duration")

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
        self.assertEqual("INVALID", missing.verdict)
        self.assertIn("NO_MEANINGFUL_REQUIREMENTS", [gap.code for gap in missing.gaps])
        self.assertIn("FRESHNESS_UNAVAILABLE", [gap.code for gap in missing.gaps])
        # An empty contract declares no verification, so missing machine
        # evidence is not the gap; having no requirements is.
        self.assertNotIn("NO_VERIFICATION_EVIDENCE", [gap.code for gap in missing.gaps])

        declared = generate_uid("verify")
        graph_with_spec = analyze(
            [{"uid": "req-1", "acceptance_criteria": [{"uid": "ac-1", "digest": "a" * 64}]}],
            [{"uid": "ac-1", "requirement": {"uid": "req-1", "digest": "a" * 64}, "verification_specifications": [{"uid": declared, "digest": "a" * 64}]}],
            [{"uid": "task-1", "requirements": [{"uid": "req-1", "digest": "a" * 64}]}],
            [{"uid": declared, "relationship": "direct_scope", "covered_implementation_paths": ["src/**"]}],
        )
        unverified = converge(graph_with_spec, [], freshness=FreshnessResult(frozenset()), trust=TrustVerdict(True, "TRUSTED"))
        self.assertIn("NO_VERIFICATION_EVIDENCE", [gap.code for gap in unverified.gaps])
        # A human-approval specification expects no run, so its absence is not one.
        human = analyze(
            [{"uid": "req-1", "acceptance_criteria": [{"uid": "ac-1", "digest": "a" * 64}]}],
            [{"uid": "ac-1", "requirement": {"uid": "req-1", "digest": "a" * 64}, "verification_specifications": [{"uid": declared, "digest": "a" * 64}]}],
            [{"uid": "task-1", "requirements": [{"uid": "req-1", "digest": "a" * 64}]}],
            [{"uid": declared, "relationship": "human_approval", "approval_predicate": {"predicate_id": "signoff", "policy_digest": "a" * 64}}],
        )
        approved_only = converge(human, [], freshness=FreshnessResult(frozenset()), trust=TrustVerdict(True, "TRUSTED"), machine_specs=frozenset())
        self.assertNotIn("NO_VERIFICATION_EVIDENCE", [gap.code for gap in approved_only.gaps])
        self.assertIn("UNVERIFIED_SPECIFICATION", [gap.code for gap in approved_only.gaps])
        forged = converge(graph, [{"uid": "run-1", "status": "PASS"}])
        self.assertEqual("INVALID", forged.verdict)
        self.assertIn("INVALID_VERIFICATION_EVIDENCE", [gap.code for gap in forged.gaps])
        stale = converge(graph, [{"uid": "run-1", "status": "PASS"}], freshness=FreshnessResult(frozenset({"POLICY_CHANGED"})))
        self.assertNotEqual("CONVERGED", stale.verdict)

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
        self.assertEqual("TRUSTED", evaluate_trust(evidence, policy=policy, approval_root=root, evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED).code)

        parent = dict(root)
        parent["uid"] = generate_uid("root")
        parent["root_digest"] = approval_root_commitment(parent)
        unauthorized = dict(root)
        unauthorized["predecessor"] = {"uid": parent["uid"], "digest": parent["root_digest"]}
        unauthorized["root_digest"] = approval_root_commitment(unauthorized)

        chained_root = dict(unauthorized)
        chained_root["transition_approval"] = {
            "predicate_id": policy["approval_predicate"]["predicate_id"], "approved_by": "release-board",
            "provenance": "GIT_REVIEWED", "successor_uid": chained_root["uid"],
            "predecessor_digest": parent["root_digest"], "policy_digest": policy["approval_predicate"]["policy_digest"],
            "successor_commitment": "0" * 64,
        }
        chained_root["transition_approval"]["successor_commitment"] = successor_commitment(chained_root)
        chained_root["root_digest"] = approval_root_commitment(chained_root)
        chained_binding = dict(binding)
        chained_binding["approval_root"] = {"uid": chained_root["uid"], "digest": chained_root["root_digest"]}
        with tempfile.TemporaryDirectory() as directory:
            chained_evidence = VerificationRunner(registry).run("check", cwd=directory, binding=chained_binding)
        self.assertEqual("ROOT_OF_TRUST_INVALID", evaluate_trust(chained_evidence, policy=policy, approval_root=chained_root, evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED).code)
        self.assertEqual("TRUSTED", evaluate_trust(chained_evidence, policy=policy, approval_root=chained_root, approval_chain=[parent], evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED).code)

        # A62: pointing at a predecessor is lineage, not consent.
        unauthorized_binding = dict(binding)
        unauthorized_binding["approval_root"] = {"uid": unauthorized["uid"], "digest": unauthorized["root_digest"]}
        with tempfile.TemporaryDirectory() as directory:
            unauthorized_evidence = VerificationRunner(registry).run("check", cwd=directory, binding=unauthorized_binding)
        self.assertEqual("ROOT_OF_TRUST_INVALID", evaluate_trust(unauthorized_evidence, policy=policy, approval_root=unauthorized, approval_chain=[parent], evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED).code)

        # A86: the successor's content changes while its UID and approval stay.
        rewritten = dict(chained_root)
        rewritten["bootstrap"] = {"initialized_at": "2026-09-03T00:00:00Z", "initialized_by": "someone else"}
        rewritten["root_digest"] = approval_root_commitment(rewritten)
        rewritten_binding = dict(binding)
        rewritten_binding["approval_root"] = {"uid": rewritten["uid"], "digest": rewritten["root_digest"]}
        with tempfile.TemporaryDirectory() as directory:
            rewritten_evidence = VerificationRunner(registry).run("check", cwd=directory, binding=rewritten_binding)
        self.assertEqual("ROOT_OF_TRUST_INVALID", evaluate_trust(rewritten_evidence, policy=policy, approval_root=rewritten, approval_chain=[parent], evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED).code)

        invalid_policy = dict(policy)
        invalid_policy["approval_predicate"] = dict(policy["approval_predicate"])
        invalid_policy["approval_predicate"]["policy_digest"] = "b" * 64
        self.assertEqual("POLICY_COMMITMENT_INVALID", evaluate_trust(evidence, policy=invalid_policy, approval_root=root, evidence_facts=ESTABLISHED, authority_facts=ESTABLISHED).code)

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


    def test_convergence_requires_evidence_bound_to_declared_specifications(self):
        registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('ok')"]}}}
        digest = "a" * 64
        declared = generate_uid("verify")
        graph = analyze(
            [{"uid": "req-1", "acceptance_criteria": [{"uid": "ac-1", "digest": digest}]}],
            [{"uid": "ac-1", "requirement": {"uid": "req-1", "digest": digest}, "verification_specifications": [{"uid": declared, "digest": digest}]}],
            [{"uid": "task-1", "requirements": [{"uid": "req-1", "digest": digest}]}],
            [{"uid": declared, "relationship": "direct_scope", "covered_implementation_paths": ["src/**"]}],
        )
        self.assertEqual((), graph.gaps)
        trusted = TrustVerdict(True, "TRUSTED")
        fresh = FreshnessResult(frozenset())

        with tempfile.TemporaryDirectory() as directory:
            unrelated = VerificationRunner(registry).run("check", cwd=directory, binding=self.binding(registry))
        self.assertEqual("PASS", unrelated.result)
        rejected = converge(graph, [unrelated], freshness=fresh, trust=trusted)
        codes = [gap.code for gap in rejected.gaps]
        self.assertEqual("NOT_CONVERGED", rejected.verdict)
        self.assertIn("UNRELATED_VERIFICATION_EVIDENCE", codes)
        self.assertIn("UNVERIFIED_SPECIFICATION", codes)

        bound_binding = self.binding(registry)
        bound_binding["verification_specification"] = {"uid": declared, "digest": digest}
        with tempfile.TemporaryDirectory() as directory:
            bound = VerificationRunner(registry).run("check", cwd=directory, binding=bound_binding)
        self.assertEqual("CONVERGED", converge(graph, [bound], freshness=fresh, trust=trusted).verdict)


    def test_verdicts_separate_unevaluable_inputs_from_unfinished_work(self):
        digest = "a" * 64
        declared = generate_uid("verify")
        graph = analyze(
            [{"uid": "req-1", "acceptance_criteria": [{"uid": "ac-1", "digest": digest}]}],
            [{"uid": "ac-1", "requirement": {"uid": "req-1", "digest": digest}, "verification_specifications": [{"uid": declared, "digest": digest}]}],
            [{"uid": "task-1", "requirements": [{"uid": "req-1", "digest": digest}]}],
            [{"uid": declared, "relationship": "direct_scope", "covered_implementation_paths": ["src/**"]}],
        )
        fresh = FreshnessResult(frozenset())
        trusted = TrustVerdict(True, "TRUSTED")

        unfinished = converge(graph, [], freshness=fresh, trust=trusted)
        self.assertEqual("NOT_CONVERGED", unfinished.verdict)
        self.assertIn("UNVERIFIED_SPECIFICATION", [gap.code for gap in unfinished.gaps])

        self.assertEqual("INVALID", converge(graph, [], freshness=fresh, trust=None).verdict)
        self.assertEqual("INVALID", converge(graph, [], freshness=None, trust=trusted).verdict)

        def exploding():
            raise MemoryError("simulated engine failure")
            yield

        broken = converge(graph, exploding(), freshness=fresh, trust=trusted)
        self.assertEqual("INTERNAL_ERROR", broken.verdict)
        self.assertIn("MemoryError", broken.reason)
        self.assertEqual((), broken.gaps)

        self.assertEqual({"CONVERGED": 0, "NOT_CONVERGED": 1, "INVALID": 2, "INTERNAL_ERROR": 3}, VERDICT_EXIT_CODES)
