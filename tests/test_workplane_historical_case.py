import json
import tempfile
import unittest
from pathlib import Path

from scripts.workplane_historical_case import CaseError, record, reveal, seal

DEFECT = "the defect: an off-by-one in the retry loop"


class HistoricalCaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        bundle = root / "bundle"
        bundle.mkdir()
        (bundle / "issue.md").write_text("what was known at the time", encoding="utf-8")
        (bundle / "requirement.md").write_text("the requirement as it stood", encoding="utf-8")
        self.bundle = bundle
        self.defect = root / "defect.txt"
        self.defect.write_text(DEFECT, encoding="utf-8")
        self.contract = root / "contract.json"
        self.contract.write_text(json.dumps({"uid": "work_01"}), encoding="utf-8")
        self.verdict = root / "verdict.json"
        self.verdict.write_text(json.dumps({"verdict": "NOT_CONVERGED"}), encoding="utf-8")
        self.case = root / "case.json"
        self.root = root

    def sealed(self):
        return seal(issue="GH-42", pre_fix_commit="deadbeef", defect=self.defect, bundle=self.bundle, output=self.case)

    def test_the_sealed_case_never_contains_the_defect_itself(self):
        case = self.sealed()
        self.assertNotIn(DEFECT, self.case.read_text(encoding="utf-8"))
        self.assertEqual(64, len(case["defect_digest"]))
        self.assertEqual(64, len(case["input_bundle_digest"]))
        self.assertIsNone(case["verdict"])

    def test_an_empty_bundle_is_refused(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(CaseError, "EMPTY_BUNDLE"):
            seal(issue="GH-42", pre_fix_commit="deadbeef", defect=self.defect, bundle=empty, output=self.case)

    def test_the_defect_cannot_be_revealed_before_a_verdict_is_frozen(self):
        self.sealed()
        with self.assertRaisesRegex(CaseError, "NO_FROZEN_VERDICT"):
            reveal(case_path=self.case, defect=self.defect, classification="DETECTED")

    def test_a_verdict_freezes_once(self):
        self.sealed()
        record(case_path=self.case, contract=self.contract, verdict=self.verdict)
        with self.assertRaisesRegex(CaseError, "VERDICT_ALREADY_FROZEN"):
            record(case_path=self.case, contract=self.contract, verdict=self.verdict)

    def test_a_substituted_defect_is_refused(self):
        self.sealed()
        record(case_path=self.case, contract=self.contract, verdict=self.verdict)
        other = self.root / "other.txt"
        other.write_text("a defect nobody sealed", encoding="utf-8")
        with self.assertRaisesRegex(CaseError, "DEFECT_DOES_NOT_MATCH_SEAL"):
            reveal(case_path=self.case, defect=other, classification="DETECTED")

    def test_the_classification_is_a_closed_set(self):
        self.sealed()
        record(case_path=self.case, contract=self.contract, verdict=self.verdict)
        with self.assertRaisesRegex(CaseError, "UNKNOWN_CLASSIFICATION"):
            reveal(case_path=self.case, defect=self.defect, classification="PROBABLY_FINE")

    def test_a_completed_case_proves_the_verdict_preceded_the_disclosure(self):
        self.sealed()
        # The proof of ordering is structural, not temporal: reveal refuses
        # until a verdict is frozen, and a frozen verdict cannot be rewritten.
        # Timestamps are metadata — on a coarse clock the two can be equal.
        with self.assertRaisesRegex(CaseError, "NO_FROZEN_VERDICT"):
            reveal(case_path=self.case, defect=self.defect, classification="DETECTED")
        recorded = record(case_path=self.case, contract=self.contract, verdict=self.verdict)
        self.assertEqual("NOT_CONVERGED", recorded["verdict"])
        revealed = reveal(case_path=self.case, defect=self.defect, classification="MISSED")
        self.assertEqual("MISSED", revealed["classification"])
        self.assertEqual(recorded["verdict_digest"], revealed["verdict_digest"], "the verdict changed across the reveal")
        self.assertGreaterEqual(revealed["revealed_at"], revealed["recorded_at"])
        with self.assertRaisesRegex(CaseError, "ALREADY_REVEALED"):
            reveal(case_path=self.case, defect=self.defect, classification="DETECTED")


if __name__ == "__main__":
    unittest.main()
