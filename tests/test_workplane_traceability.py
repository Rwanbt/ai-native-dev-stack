import unittest

from ainative_workplane.traceability import analyze


def ref(uid):
    return {"uid": uid, "digest": "a" * 64}


class TraceabilityTests(unittest.TestCase):
    def test_complete_graph_has_no_gaps(self):
        result = analyze(
            [{"uid": "req-1", "acceptance_criteria": [ref("ac-1")] }],
            [{"uid": "ac-1", "requirement": ref("req-1"), "verification_specifications": [ref("verify-1")] }],
            [{"uid": "task-1", "requirements": [ref("req-1")] }],
            [{"uid": "verify-1"}],
        )
        self.assertTrue(result.is_structurally_valid)
        self.assertEqual((("req-1", "ac-1"),), result.requirement_to_acceptance)

    def test_gap_detection_is_deterministic_and_non_semantic(self):
        result = analyze(
            [{"uid": "req-1", "acceptance_criteria": [ref("ac-1")] }, {"uid": "req-2", "acceptance_criteria": []}],
            [{"uid": "ac-1", "requirement": ref("req-1"), "verification_specifications": []}],
            [{"uid": "task-1", "requirements": [ref("missing")] }],
            [{"uid": "verify-orphan"}],
        )
        codes = [gap.code for gap in result.gaps]
        self.assertIn("UNVERIFIABLE_ACCEPTANCE", codes)
        self.assertIn("REQ_WITHOUT_ACCEPTANCE", codes)
        self.assertIn("TASK_WITHOUT_VERIFICATION", codes)
        self.assertIn("REQ_WITHOUT_TASK", codes)
        self.assertIn("BROKEN_REFERENCE", codes)
        self.assertIn("ORPHAN_VERIFICATION_SPEC", codes)
        self.assertEqual(result, analyze(
            [{"uid": "req-1", "acceptance_criteria": [ref("ac-1")] }, {"uid": "req-2", "acceptance_criteria": []}],
            [{"uid": "ac-1", "requirement": ref("req-1"), "verification_specifications": []}],
            [{"uid": "task-1", "requirements": [ref("missing")] }],
            [{"uid": "verify-orphan"}],
        ))
