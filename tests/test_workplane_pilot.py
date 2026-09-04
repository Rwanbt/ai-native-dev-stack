"""The pilot instrument: what it measures, and what it refuses to claim.

The harness this replaced called the pure `converge()` kernel with a
hand-built trust verdict and a hand-built freshness result, then reported
CONVERGED five times. It measured nothing about authority, and it could not
have failed. These cases exist so that the replacement cannot quietly become
that again.
"""

import ast
import json
import tempfile
import unittest
from pathlib import Path

from scripts import workplane_pilot
from scripts.workplane_pilot import PilotItem, assess_plan, measure, run_plan, self_check
from tests.test_workplane_authority import GovernedWork

# Names that would mean the instrument is deciding something it must only
# observe. A harness that constructs its own trust or freshness, builds
# evidence, or calls the pure kernel is reporting its own opinion.
FORBIDDEN = {"converge", "evaluate_trust", "evaluate_authority_trust", "evaluate_freshness", "TrustVerdict", "FreshnessResult", "VerificationEvidence", "VerificationRunner", "policy_commitment", "approval_root_commitment"}


class InstrumentBoundaryTests(unittest.TestCase):
    """The instrument may observe the production surface. It may not be one."""

    def imported_names(self):
        source = Path(workplane_pilot.__file__).read_text(encoding="utf-8")
        names = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
        return names

    def test_the_instrument_injects_no_authority(self):
        leaked = FORBIDDEN & self.imported_names()
        self.assertEqual(set(), leaked, f"the pilot harness imports {sorted(leaked)}, which it must only observe")

    def test_the_instrument_reports_the_production_surface(self):
        record = run_plan({"pilot_id": "empty", "items": []})
        self.assertEqual("evaluate_work", record["surface"])
        self.assertEqual("production_boundary", record["authority"])

    def test_an_empty_plan_is_not_pilot_evidence(self):
        record = run_plan({"pilot_id": "empty", "items": []})
        self.assertFalse(record["pilot_evidence"])
        self.assertTrue(record["pilot_evidence_refusals"])


class InstrumentMeasurementTests(unittest.TestCase):
    def governed(self, **kwargs):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        return GovernedWork(Path(directory.name), **kwargs)

    def item(self, work, **overrides):
        declared = {"expected_verdict": "CONVERGED"}
        declared.update(overrides.pop("declared", {}))
        return PilotItem.parse({
            "kind": "feature", "harness_id": "test", "work_dir": str(work.work),
            "repository_root": str(work.repo), "declared": declared, **overrides,
        })

    def test_a_converging_work_is_measured_through_the_production_boundary(self):
        work = self.governed()
        record = measure(self.item(work))
        self.assertIsNone(record["harness_error"])
        measured = record["measured"]
        self.assertEqual("CONVERGED", measured["verdict"])
        self.assertTrue(measured["authority_established"])
        self.assertEqual(1, measured["verification_runs"])
        self.assertEqual(1, measured["eligible_runs"])
        self.assertEqual(1, measured["contract_revisions"])
        self.assertTrue(measured["contract_intact"])
        self.assertIsNotNone(measured["verification_runtime_ms"])
        self.assertEqual(40, len(measured["repository_head"]))
        self.assertTrue(record["assessed"]["verdict_matches_expectation"])

    def test_unestablished_authority_is_recorded_as_such_and_runs_nothing(self):
        work = self.governed(anchor=False)
        record = measure(self.item(work))
        measured = record["measured"]
        self.assertEqual("INVALID", measured["verdict"])
        self.assertFalse(measured["authority_established"])
        self.assertIn("PROJECT_TRUST_UNINITIALIZED", measured["authority_refusal"])
        self.assertEqual(0, measured["verification_runs"])
        self.assertIn("PROJECT_TRUST_UNINITIALIZED", [gap["code"] for gap in measured["gaps"]])

    def test_a_verdict_that_contradicts_the_declaration_is_flagged(self):
        work = self.governed(anchor=False)
        record = measure(self.item(work))
        self.assertFalse(record["assessed"]["verdict_matches_expectation"])
        self.assertTrue(record["assessed"]["false_not_converged"])
        self.assertFalse(record["assessed"]["false_converged"])

    def test_a_false_converged_is_what_the_instrument_is_watching_for(self):
        work = self.governed()
        record = measure(self.item(work, declared={"expected_verdict": "NOT_CONVERGED"}))
        self.assertEqual("CONVERGED", record["measured"]["verdict"])
        self.assertTrue(record["assessed"]["false_converged"])

    def test_normative_mutations_count_the_approvals_the_work_needed(self):
        work = self.governed()
        second = work.with_second_verification(command="other", script="print('Ran 1 test in 0.0s'); print('OK')\n")
        self.assertTrue(second)
        record = measure(self.item(work))
        measured = record["measured"]
        self.assertEqual(2, measured["contract_revisions"])
        self.assertEqual(1, measured["normative_mutations"])

    def test_an_unreadable_work_is_a_harness_error_not_a_verdict(self):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        item = PilotItem.parse({"kind": "feature", "harness_id": "test", "work_dir": str(Path(directory.name) / "nothing"), "repository_root": directory.name, "declared": {"expected_verdict": "CONVERGED"}})
        record = measure(item)
        self.assertIsNotNone(record["harness_error"])
        self.assertNotIn("measured", record)


class PilotEvidenceRefusalTests(unittest.TestCase):
    """The instrument cannot be used to claim a gate it has not measured."""

    def plan_items(self, kinds, harnesses, synthetic=False):
        return [
            PilotItem.parse({
                "kind": kind, "harness_id": harnesses[index % len(harnesses)],
                "work_dir": f"/work/{index}", "repository_root": "/repo",
                "synthetic": synthetic, "declared": {"expected_verdict": "CONVERGED"},
            })
            for index, kind in enumerate(kinds)
        ]

    def records(self, items, error=None):
        return [{"kind": item.kind, "harness_error": error, "declared": item.declared} for item in items]

    def test_a_complete_real_two_harness_plan_is_evidence(self):
        items = self.plan_items(list(workplane_pilot.REQUIRED_KINDS), ["claude-code", "opencode"])
        evidence, refusals = assess_plan(items, self.records(items))
        self.assertTrue(evidence, refusals)
        self.assertEqual([], refusals)

    def test_one_harness_is_not_two(self):
        items = self.plan_items(list(workplane_pilot.REQUIRED_KINDS), ["claude-code"])
        evidence, refusals = assess_plan(items, self.records(items))
        self.assertFalse(evidence)
        self.assertTrue(any("distinct harnesses" in refusal for refusal in refusals))

    def test_synthetic_items_are_never_evidence(self):
        items = self.plan_items(list(workplane_pilot.REQUIRED_KINDS), ["claude-code", "opencode"], synthetic=True)
        evidence, refusals = assess_plan(items, self.records(items))
        self.assertFalse(evidence)
        self.assertTrue(any("real work items" in refusal for refusal in refusals))

    def test_the_five_kinds_are_required(self):
        items = self.plan_items(["feature"] * 5, ["claude-code", "opencode"])
        evidence, refusals = assess_plan(items, self.records(items))
        self.assertFalse(evidence)
        self.assertTrue(any("the protocol needs" in refusal for refusal in refusals))

    def test_an_item_the_instrument_could_not_measure_blocks_evidence(self):
        items = self.plan_items(list(workplane_pilot.REQUIRED_KINDS), ["claude-code", "opencode"])
        evidence, refusals = assess_plan(items, self.records(items, error="boom"))
        self.assertFalse(evidence)
        self.assertTrue(any("could not measure" in refusal for refusal in refusals))

    def test_an_item_with_no_declared_expectation_blocks_evidence(self):
        """Without an expectation, a false verdict is undetectable."""

        items = self.plan_items(list(workplane_pilot.REQUIRED_KINDS), ["claude-code", "opencode"])
        records = [{"kind": item.kind, "harness_error": None, "declared": {}} for item in items]
        evidence, refusals = assess_plan(items, records)
        self.assertFalse(evidence)
        self.assertTrue(any("no expected verdict" in refusal for refusal in refusals))


class SelfCheckTests(unittest.TestCase):
    def test_the_self_check_measures_a_real_boundary_and_claims_nothing(self):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        record = self_check(Path(directory.name))
        self.assertEqual("evaluate_work", record["surface"])
        self.assertEqual(1, record["converged"])
        self.assertEqual([], record["harness_errors"])
        self.assertFalse(record["pilot_evidence"])
        self.assertTrue(any("synthetic" in refusal for refusal in record["pilot_evidence_refusals"]))

    def test_the_cli_refuses_both_modes_at_once(self):
        with self.assertRaises(SystemExit):
            workplane_pilot.main([])
        with self.assertRaises(SystemExit):
            workplane_pilot.main(["--self-check", "--plan", "plan.json"])

    def test_the_cli_writes_the_record_it_prints(self):
        directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(directory.cleanup)
        output = Path(directory.name) / "record.json"
        self.assertEqual(0, workplane_pilot.main(["--self-check", "--output", str(output)]))
        self.assertFalse(json.loads(output.read_text(encoding="utf-8"))["pilot_evidence"])


if __name__ == "__main__":
    unittest.main()
