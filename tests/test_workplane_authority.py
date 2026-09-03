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

    def __init__(self, root: Path, *, required=None):
        self.root = root
        self.repo = root / "repo"
        # The work directory lives in the repository it governs. That is what
        # gives its artifacts a provenance of their own: changing the rules
        # means committing the change, where it can be seen.
        self.work = self.repo / ".ai-native" / "work" / "w1"
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
        self.required = {"git_recorded": True} if required is None else required
        self.policy = self._policy(self.required)
        self.commitment = policy_commitment(self.policy)
        for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
            self.policy[field]["policy_digest"] = self.commitment
        self.approval_root = {
            "schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"),
            "root_digest": DIGEST, "policy_digest": self.commitment, "root_provenance": "GIT_RECORDED",
            "bootstrap": {"initialized_at": "2026-09-03T00:00:00Z", "initialized_by": "authority-test"},
        }
        self.approval_root["root_digest"] = approval_root_commitment(self.approval_root)
        WorkController(self.work).create(self.artifacts())
        self.commit_governed_state()

    def commit_governed_state(self):
        """Record the governed state, as a real project would."""

        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "governed state")

    def _policy(self, required):
        return {
            "schema_name": "project_policy", "schema_version": 1,
            "approval_predicate": {"predicate_id": "review", "policy_digest": DIGEST},
            "required_mutation_facts": required,
            "required_evidence_facts": required,
            "waiver_approval_rule": {"predicate_id": "waiver-board", "policy_digest": DIGEST},
            "human_approval_rule": {"predicate_id": "human-signoff", "policy_digest": DIGEST},
            "promotion_policy": "explicit",
        }

    def specification(self, **overrides):
        declared = {
            "schema_name": "verification_specification", "schema_version": 1, "uid": overrides.pop("uid", self.specification_uid),
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

    def with_second_verification(self, *, command, script):
        """Add a second declared verification with its own command."""

        (self.repo / "tests" / "other.py").write_text(script, encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "second check")
        second_uid = generate_uid("verify")
        second_criterion = generate_uid("ac")
        artifacts = self.artifacts()
        registry = self.registry()
        registry["commands"][command] = {"argv": [sys.executable, "tests/other.py"], "timeout_seconds": 30, "substance": {"type": "unittest", "minimum_observations": 1}}
        artifacts["command_registry"] = registry
        artifacts["acceptance_criteria"] = artifacts["acceptance_criteria"] + [{
            "schema_name": "acceptance_criteria", "schema_version": 1, "uid": second_criterion,
            "requirement": {"uid": self.requirement_uid, "digest": DIGEST},
            "criterion": "the second check holds",
            "verification_specifications": [{"uid": second_uid, "digest": DIGEST}],
        }]
        artifacts["requirements"] = [dict(artifacts["requirements"][0], acceptance_criteria=[{"uid": self.criterion_uid, "digest": DIGEST}, {"uid": second_criterion, "digest": DIGEST}])]
        artifacts["verification_specifications"] = artifacts["verification_specifications"] + [self.specification(uid=second_uid, command=command, execution_scope=["tests/other.py"])]
        WorkController(self.work).mutate(1, artifacts)
        self.commit_governed_state()
        return second_uid

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
        self.assertTrue(evaluation.provenance.git_recorded)
        self.assertTrue(evaluation.authority_provenance.git_recorded, evaluation.authority_provenance.reason)

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
        work = self.governed(required={"ci_verified": True})
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

    def test_a57_a_checkout_that_moves_during_the_run_is_not_fresh(self):
        # Re-execution means evidence is always current for a still checkout.
        # What freshness still catches is the checkout moving underneath a run:
        # a race, not a staleness gate. Said plainly rather than implied.
        work = self.governed()
        target = str(work.repo / "src" / "app.py").replace("\\", "\\\\")
        moving = (
            "import pathlib\n"
            "pathlib.Path(r'" + target + "').write_text('VALUE = 2\\n')\n"
            "print('Ran 1 test in 0.0s')\n"
            "print('OK')\n"
        )
        (work.repo / "tests" / "check.py").write_text(moving, encoding="utf-8")
        git(work.repo, "commit", "-am", "the check rewrites its own dependency")
        evaluation = work.evaluate()
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict)
        self.assertIn("STALE_DEPENDENCY", evaluation.assessments[0].reasons)

    def test_a58_a59_a_passing_verification_never_carries_a_failing_one(self):
        work = self.governed()
        failing = "import sys\nprint('Ran 1 test in 0.0s')\nprint('FAILED (failures=1)')\nsys.exit(1)\n"
        second_uid = work.with_second_verification(command="other", script=failing)
        evaluation = work.evaluate()
        self.assertEqual(2, len(evaluation.assessments), [a.reasons for a in evaluation.assessments])
        by_spec = {assessment.verification_spec_uid: assessment for assessment in evaluation.assessments}
        self.assertTrue(by_spec[work.specification_uid].eligible, by_spec[work.specification_uid].reasons)
        self.assertFalse(by_spec[second_uid].eligible, "a failing run inherited the passing one's standing")
        self.assertIn("VERIFICATION_FAILED", by_spec[second_uid].reasons)
        self.assertNotEqual("CONVERGED", evaluation.verdict.verdict)

    def test_a60_a69_a70_a87_a88_every_binding_identity_is_checked(self):
        # Evidence is produced in process, so these are checked where they
        # still apply: the binding comparison itself.
        from ainative_workplane.evaluator import _binding_reasons

        work = self.governed()
        evidence = work.verify().artifact
        current = {
            "spec_digest": evidence["verification_specification"]["digest"],
            "contract_digest": evidence["contract_digest"],
            "registry_digest": evidence["command_registry_digest"],
            "policy_digest": evidence["policy_digest"],
            "root_reference": evidence["approval_root"],
            "work_uid": evidence["work"]["uid"],
            "revision": evidence["contract_revision"],
        }
        self.assertEqual([], _binding_reasons(evidence, **current))
        for case, override, expected in (
            ("A60 wrong spec digest", {"spec_digest": "b" * 64}, "VERIFICATION_SPEC_CHANGED"),
            ("A60 unknown spec", {"spec_digest": None}, "UNRELATED_VERIFICATION_EVIDENCE"),
            ("A69 wrong root", {"root_reference": {"uid": generate_uid("root"), "digest": "b" * 64}}, "ROOT_OF_TRUST_CHANGED"),
            ("A70 wrong policy", {"policy_digest": "b" * 64}, "POLICY_CHANGED"),
            ("A87 wrong revision", {"revision": 99}, "STALE_CONTRACT_REVISION"),
            ("A88 wrong work", {"work_uid": generate_uid("work")}, "UNRELATED_WORK"),
            ("wrong registry", {"registry_digest": "b" * 64}, "COMMAND_REGISTRY_CHANGED"),
            ("wrong contract", {"contract_digest": "b" * 64}, "STALE_CONTRACT"),
        ):
            with self.subTest(case=case):
                self.assertIn(expected, _binding_reasons(evidence, **{**current, **override}))

    def test_a65_a66_the_production_api_takes_no_verdict_objects(self):
        from inspect import signature

        parameters = set(signature(evaluate_work).parameters)
        self.assertEqual({"work_dir", "repository_root"}, parameters)
        for forbidden in ("trust", "freshness", "policy", "contract", "approval_root", "registry"):
            self.assertNotIn(forbidden, parameters, f"the authoritative API accepts {forbidden} from its caller")

    def test_a67_a_waiver_cannot_suppress_an_authority_gap(self):
        work = self.governed(required={"ci_verified": True})
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
