"""Authority attacks A72-A90: who may create evidence, and who may change the rules.

The A54-A70 matrix proved that the evaluator does not accept authority from its
caller's arguments. These cases ask the next question: can a caller manufacture
the things the evaluator does accept — a verification result, a provenance
claim, an approval, or a weaker rule to be measured against.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.controller import ControllerError, WorkController
from ainative_workplane.evaluator import SUCCESS_CONDITION, EvaluationError, evaluate_work
from ainative_workplane.snapshot import build_repository_snapshot, snapshot_reference
from ainative_workplane.trust import policy_commitment
from tests.test_workplane_authority import GovernedWork


def forged_run(work: GovernedWork, **overrides):
    """Build a complete, schema-valid PASS run without executing anything.

    Every value is read from committed state and from the checkout, which is
    exactly what an agent with write access to the work directory can do.
    """

    manifest, artifacts = WorkController(work.work).load_committed_artifacts()
    specification = artifacts["verification_specifications"][0]
    policy_digest = policy_commitment(artifacts["project_policy"])
    registry_digest = canonical_digest(artifacts["command_registry"])
    root = artifacts["approval_root"]
    contract_digest = canonical_digest({name: artifacts.get(name, []) for name in SUCCESS_CONDITION})
    snapshot = build_repository_snapshot(
        work.repo,
        scope=specification["execution_scope"],
        dependency_paths=specification["covered_implementation_paths"],
        command_registry_digest=registry_digest,
        policy_digest=policy_digest,
    )
    record = {
        "schema_name": "verification_run", "schema_version": 1, "uid": generate_uid("run"),
        "work": {"uid": manifest["work_uid"], "digest": contract_digest},
        "contract_revision": manifest["revision"], "contract_digest": contract_digest,
        "verification_specification": {"uid": specification["uid"], "digest": canonical_digest(specification)},
        "command_registry_digest": registry_digest, "policy_digest": policy_digest,
        "approval_root": {"uid": root["uid"], "digest": root["root_digest"]},
        "repository_snapshot": snapshot_reference(snapshot),
        "snapshot_content_digest": snapshot["content_digest"],
        "snapshot_dependency_digest": snapshot["dependency_digest"],
        "snapshot_head": snapshot["head"],
        "producer": "ainative-workplane", "producer_version": "0.1.0",
        "command": "check", "result": "PASS", "exit_code": 0,
        "started_at": "2026-09-03T00:00:00Z", "finished_at": "2026-09-03T00:00:01Z", "duration_ms": 1,
        "stdout_digest": "0" * 64, "stderr_digest": "0" * 64,
        "substance_metadata": {"adapter": "unittest", "tests_executed": 999},
        "evidence_provenance": "GIT_RECORDED",
    }
    record.update(overrides)
    return record


class EvidenceOriginTests(unittest.TestCase):
    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def test_a72_a_hand_written_run_is_never_read(self):
        work = self.governed()
        runs = work.work / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        forged = forged_run(work)
        (runs / "forged.json").write_text(json.dumps(forged), encoding="utf-8")
        # Every digest in the file is correct and the checkout is clean. The
        # only thing missing is that no command was ever run — so the file must
        # carry no weight either way.
        evaluation = evaluate_work(work.work, work.repo)
        judged = {assessment.evidence_uid for assessment in evaluation.assessments}
        self.assertNotIn(forged["uid"], judged, "a hand-written run was judged as evidence")
        self.assertEqual(1, len(evaluation.assessments), "exactly the one executable specification is judged")

    def test_a72_a_forgery_cannot_hide_a_verification_that_fails(self):
        work = self.governed()
        failing = "import sys\nprint('Ran 1 test in 0.0s')\nprint('FAILED (failures=1)')\nsys.exit(1)\n"
        (work.repo / "tests" / "check.py").write_text(failing, encoding="utf-8")
        import subprocess
        subprocess.run(["git", "-C", str(work.repo), "commit", "-am", "break the check"], check=True, capture_output=True)
        runs = work.work / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "forged.json").write_text(json.dumps(forged_run(work)), encoding="utf-8")
        evaluation = evaluate_work(work.work, work.repo)
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict, "a forged PASS masked a failing verification")

    def test_a73_the_authoritative_api_takes_no_evidence_directory(self):
        from inspect import signature

        self.assertEqual({"work_dir", "repository_root"}, set(signature(evaluate_work).parameters))



class RegistrySchemaTests(unittest.TestCase):
    """A89, A90: one validator, so the controller and the runner agree."""

    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def malformed(self, work):
        return {
            "A89 no commands": {"schema_name": "command_registry", "schema_version": 1, "commands": {}},
            "A89 shell requested": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": ["echo"], "shell": True}}},
            "A89 empty argv": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": []}}},
            "A89 impossible timeout": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": ["echo"], "timeout_seconds": 0}}},
            "A89 unknown substance": {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": ["echo"], "substance": {"type": "junit"}}}},
        }

    def test_a89_a_malformed_registry_cannot_become_committed_authority(self):
        work = self.governed()
        for case, registry in self.malformed(work).items():
            with self.subTest(case=case):
                with self.assertRaises(ControllerError) as refused:
                    WorkController(work.work).mutate(1, {"command_registry": registry}, approval=work.approval_for_change({"command_registry": registry}))
                self.assertIn("INVALID_NORMATIVE_ARTIFACT:command_registry", str(refused.exception))

    def test_a90_what_the_controller_accepts_the_runner_accepts(self):
        from ainative_workplane.runner import RunnerError, load_registry
        from ainative_workplane.contracts import ContractError, validate_normative

        work = self.governed()
        for case, registry in self.malformed(work).items():
            with self.subTest(case=case):
                with self.assertRaises(ContractError):
                    validate_normative("command_registry", registry)
                with self.assertRaises(RunnerError):
                    load_registry(registry)
        # And the committed one satisfies both, by construction.
        _, artifacts = WorkController(work.work).load_committed_artifacts()
        validate_normative("command_registry", artifacts["command_registry"])
        self.assertEqual(artifacts["command_registry"], load_registry(artifacts["command_registry"]))



if __name__ == "__main__":
    unittest.main()
