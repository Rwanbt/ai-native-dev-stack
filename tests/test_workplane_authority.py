"""End-to-end authority matrix A54-A70.

These cases run through the production boundary — a real checkout, a real
governed work directory written by the controller, real verification evidence
— because what they test is composition. A helper that behaves correctly in
isolation while the assembled system converges on forged input would pass a
unit test and fail the only question that matters.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.controller import ControllerError, WorkController
from ainative_workplane.evaluator import EvaluationError, evaluate_work, run_verification
from ainative_workplane.trust import approval_root_commitment, policy_commitment

DIGEST = "a" * 64


def git(root, *arguments):
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


class GovernedWork:
    """A checkout plus a governed work directory that converges."""

    def __init__(self, root: Path, *, required="GIT_RECORDED"):
        self.root = root
        self.repo = root / "repo"
        self.work = root / "work"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repo / "tests" / "check.py").write_text("print('Ran 1 test in 0.001s'); print('OK')\n", encoding="utf-8")
        git(self.repo, "init")
        git(self.repo, "config", "user.email", "authority@example.invalid")
        git(self.repo, "config", "user.name", "Authority Test")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "initial")

        self.specification_uid = generate_uid("verify")
        self.requirement_uid = generate_uid("req")
        self.criterion_uid = generate_uid("ac")
        self.policy = self._policy(required)
        self.commitment = policy_commitment(self.policy)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            self.policy[field]["policy_digest"] = self.commitment
        self.approval_root = {
            "schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"),
            "root_digest": DIGEST, "policy_digest": self.commitment, "root_provenance": required,
            "bootstrap": {"initialized_at": "2026-09-03T00:00:00Z", "initialized_by": "authority-test"},
        }
        self.approval_root["root_digest"] = approval_root_commitment(self.approval_root)
        WorkController(self.work).create(self.artifacts())

    def _policy(self, required):
        return {
            "schema_name": "project_policy", "schema_version": 1,
            "approval_predicate": {"predicate_id": "review", "policy_digest": DIGEST},
            "success_condition_mutation_provenance": required,
            "verification_evidence_provenance": required,
            "waiver_approval_rule": {"predicate_id": "waiver-board", "policy_digest": DIGEST},
            "human_approval_rule": {"predicate_id": "human-signoff", "policy_digest": DIGEST},
            "promotion_policy": "explicit",
        }

    def specification(self, **overrides):
        declared = {
            "schema_name": "verification_specification", "schema_version": 1, "uid": self.specification_uid,
            "acceptance_criteria": [{"uid": self.criterion_uid, "digest": DIGEST}],
            "command_registry": {"uid": generate_uid("work"), "digest": DIGEST},
            "relationship": "black_box", "execution_scope": ["tests/check.py"],
            "covered_implementation_paths": ["src/app.py"], "dependencies": [],
            "substance_requirement": "unittest", "required_evidence_provenance": "GIT_RECORDED",
            "command": "check",
        }
        declared.update(overrides)
        return declared

    def registry(self):
        return {
            "schema_name": "command_registry", "schema_version": 1,
            "commands": {"check": {"argv": [sys.executable, "tests/check.py"], "timeout_seconds": 30, "substance": {"type": "unittest", "minimum_observations": 1}}},
        }

    def artifacts(self, **overrides):
        declared = {
            "requirements": [{"schema_name": "requirements", "schema_version": 1, "uid": self.requirement_uid, "statement": "the value stays one", "acceptance_criteria": [{"uid": self.criterion_uid, "digest": DIGEST}]}],
            "acceptance_criteria": [{"schema_name": "acceptance_criteria", "schema_version": 1, "uid": self.criterion_uid, "requirement": {"uid": self.requirement_uid, "digest": DIGEST}, "criterion": "the module still exposes VALUE", "verification_specifications": [{"uid": self.specification_uid, "digest": DIGEST}]}],
            "tasks": [{"schema_name": "tasks", "schema_version": 1, "uid": generate_uid("task"), "requirements": [{"uid": self.requirement_uid, "digest": DIGEST}], "implementation_paths": ["src/app.py"]}],
            "verification_specifications": [self.specification()],
            "project_policy": self.policy,
            "approval_root": self.approval_root,
            "command_registry": self.registry(),
        }
        declared.update(overrides)
        return declared

    def verify(self):
        return run_verification(self.work, self.repo, self.specification_uid)

    def evaluate(self):
        return evaluate_work(self.work, self.repo)

    def runs(self):
        return self.work / "runs"


class AuthorityMatrixTests(unittest.TestCase):
    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def codes(self, evaluation):
        return [gap.code for gap in evaluation.verdict.gaps]

    def test_the_governed_path_converges_before_anything_is_attacked(self):
        work = self.governed()
        self.assertEqual("PASS", work.verify().result)
        evaluation = work.evaluate()
        self.assertEqual("CONVERGED", evaluation.verdict.verdict, self.codes(evaluation))
        self.assertEqual(1, len(evaluation.assessments))
        self.assertTrue(evaluation.assessments[0].eligible)
        self.assertEqual("GIT_RECORDED", evaluation.provenance.level)

    def test_a54_a68_a_loose_contract_beside_the_work_directory_has_no_authority(self):
        work = self.governed()
        work.verify()
        easier = work.root / "contract.json"
        easier.write_text(json.dumps({"requirements": [], "acceptance_criteria": [], "tasks": [], "verification_specifications": []}), encoding="utf-8")
        # There is no way to name it: the evaluator takes a work directory.
        evaluation = evaluate_work(work.work, work.repo)
        self.assertEqual("CONVERGED", evaluation.verdict.verdict)
        self.assertEqual(work.evaluate().contract_digest, evaluation.contract_digest)
        # And a directory with no committed manifest cannot be authoritative.
        with self.assertRaisesRegex(EvaluationError, "NO_AUTHORITATIVE_STATE"):
            evaluate_work(work.root / "not-a-work-directory", work.repo)

    def test_a55_a56_a61_a_claimed_provenance_cannot_exceed_what_was_observed(self):
        work = self.governed(required="SIGNED")
        work.verify()
        evaluation = work.evaluate()
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict)
        self.assertIn("INELIGIBLE_VERIFICATION_EVIDENCE", self.codes(evaluation))
        reasons = evaluation.assessments[0].reasons
        self.assertIn("INSUFFICIENT_EVIDENCE_PROVENANCE", reasons)

        # The same forgery written straight into the evidence file changes nothing.
        record = json.loads(next(work.runs().glob("*.json")).read_text(encoding="utf-8"))
        record["evidence_provenance"] = "SIGNED"
        next(work.runs().glob("*.json")).write_text(json.dumps(record), encoding="utf-8")
        forged = work.evaluate()
        self.assertNotEqual("CONVERGED", forged.verdict.verdict)
        self.assertIn("INSUFFICIENT_EVIDENCE_PROVENANCE", forged.assessments[0].reasons)

    def test_a57_a_stale_scope_is_found_by_recomputation_not_by_a_fixture(self):
        work = self.governed()
        work.verify()
        self.assertEqual("CONVERGED", work.evaluate().verdict.verdict)
        (work.repo / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        stale = work.evaluate()
        self.assertNotEqual("CONVERGED", stale.verdict.verdict)
        self.assertIn("STALE_DEPENDENCY", stale.assessments[0].reasons)

    def test_a58_a59_a69_a70_a_first_good_run_never_carries_a_second_one(self):
        work = self.governed()
        work.verify()
        good = next(work.runs().glob("*.json"))
        record = json.loads(good.read_text(encoding="utf-8"))

        for case, mutation, expected in (
            ("A58 stale", {"snapshot_content_digest": "b" * 64}, "STALE_SCOPE"),
            ("A59 untrusted", {"evidence_provenance": "UNTRACKED"}, "INSUFFICIENT_EVIDENCE_PROVENANCE"),
            ("A69 wrong root", {"approval_root": {"uid": generate_uid("root"), "digest": "b" * 64}}, "ROOT_OF_TRUST_CHANGED"),
            ("A70 wrong policy", {"policy_digest": "b" * 64}, "POLICY_CHANGED"),
        ):
            with self.subTest(case=case):
                second = dict(record)
                second["uid"] = generate_uid("run")
                second.update(mutation)
                (work.runs() / f"{second['uid']}.json").write_text(json.dumps(second), encoding="utf-8")
                evaluation = work.evaluate()
                self.assertEqual(2, len(evaluation.assessments))
                weaker = [assessment for assessment in evaluation.assessments if assessment.evidence_uid == second["uid"]][0]
                self.assertFalse(weaker.eligible, f"{case} inherited the first run's standing")
                self.assertIn(expected, weaker.reasons)
                (work.runs() / f"{second['uid']}.json").unlink()

    def test_a60_the_right_specification_uid_with_the_wrong_digest_is_rejected(self):
        work = self.governed()
        work.verify()
        path = next(work.runs().glob("*.json"))
        record = json.loads(path.read_text(encoding="utf-8"))
        record["verification_specification"] = {"uid": work.specification_uid, "digest": "b" * 64}
        path.write_text(json.dumps(record), encoding="utf-8")
        evaluation = work.evaluate()
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict)
        self.assertIn("VERIFICATION_SPEC_CHANGED", evaluation.assessments[0].reasons)

    def test_a65_a66_the_production_api_takes_no_verdict_objects(self):
        from inspect import signature

        parameters = set(signature(evaluate_work).parameters)
        self.assertEqual({"work_dir", "repository_root", "evidence_dir"}, parameters)
        for forbidden in ("trust", "freshness", "policy", "contract", "approval_root", "registry"):
            self.assertNotIn(forbidden, parameters, f"the authoritative API accepts {forbidden} from its caller")

    def test_a67_a_waiver_cannot_suppress_an_authority_gap(self):
        work = self.governed(required="SIGNED")
        work.verify()
        waiver = {
            "schema_name": "waiver", "schema_version": 1, "uid": generate_uid("waiver"),
            "target": {"uid": work.specification_uid, "digest": DIGEST}, "reason": "ship it",
            "scope": "INELIGIBLE_VERIFICATION_EVIDENCE", "approved_by": "someone",
            "approved_at": "2026-09-03T00:00:00Z", "state": "effective",
            "approval_provenance": "GIT_REVIEWED",
            "approval_predicate": {"predicate_id": "waiver-board", "policy_digest": work.commitment},
            "policy_digest": work.commitment,
        }
        WorkController(work.work).mutate(1, {"waivers": [waiver]})
        evaluation = work.evaluate()
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict)

    def test_a62_a_root_successor_without_transition_approval_is_refused(self):
        work = self.governed()
        successor = dict(work.approval_root)
        successor["uid"] = generate_uid("root")
        successor["predecessor"] = {"uid": work.approval_root["uid"], "digest": work.approval_root["root_digest"]}
        successor["root_digest"] = approval_root_commitment(successor)
        with self.assertRaisesRegex(ControllerError, "INVALID_NORMATIVE_ARTIFACT"):
            WorkController(work.work).mutate(1, {"approval_root": successor})


if __name__ == "__main__":
    unittest.main()
