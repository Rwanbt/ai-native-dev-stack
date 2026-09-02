import unittest

from ainative_workplane.traceability import analyze


def ref(uid):
    return {"uid": uid, "digest": "a" * 64}


def spec(uid, relationship="direct_scope", **fields):
    declared = {"uid": uid, "relationship": relationship}
    declared.setdefault("covered_implementation_paths", ["src/**"])
    declared.update(fields)
    return declared


class TraceabilityTests(unittest.TestCase):
    def test_complete_graph_has_no_gaps(self):
        result = analyze(
            [{"uid": "req-1", "acceptance_criteria": [ref("ac-1")] }],
            [{"uid": "ac-1", "requirement": ref("req-1"), "verification_specifications": [ref("verify-1")] }],
            [{"uid": "task-1", "requirements": [ref("req-1")], "implementation_paths": ["src/app.py"]}],
            [spec("verify-1")],
        )
        self.assertTrue(result.is_structurally_valid, [gap.code for gap in result.gaps])
        self.assertEqual((("req-1", "ac-1"),), result.requirement_to_acceptance)

    def test_gap_detection_is_deterministic_and_non_semantic(self):
        result = analyze(
            [{"uid": "req-1", "acceptance_criteria": [ref("ac-1")] }, {"uid": "req-2", "acceptance_criteria": []}],
            [{"uid": "ac-1", "requirement": ref("req-1"), "verification_specifications": []}],
            [{"uid": "task-1", "requirements": [ref("missing")] }],
            [spec("verify-orphan")],
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
            [spec("verify-orphan")],
        ))

    def test_relationship_decides_what_coverage_a_specification_must_declare(self):
        def graph(declared, task_paths=("src/api/handler.py",)):
            return analyze(
                [{"uid": "req-1", "acceptance_criteria": [ref("ac-1")]}],
                [{"uid": "ac-1", "requirement": ref("req-1"), "verification_specifications": [ref("verify-1")]}],
                [{"uid": "task-1", "requirements": [ref("req-1")], "implementation_paths": list(task_paths)}],
                [declared],
            )

        self.assertIn("INVALID_VERIFICATION_RELATIONSHIP", [gap.code for gap in graph({"uid": "verify-1"}).gaps])
        self.assertIn("INVALID_VERIFICATION_RELATIONSHIP", [gap.code for gap in graph({"uid": "verify-1", "relationship": "vibes"}).gaps])

        uncovered = graph(spec("verify-1", covered_implementation_paths=["src/ui/**"]))
        self.assertIn("INSUFFICIENT_VERIFICATION_SCOPE", [gap.code for gap in uncovered.gaps])
        covered = graph(spec("verify-1", covered_implementation_paths=["src/api/**"]))
        self.assertTrue(covered.is_structurally_valid, [gap.code for gap in covered.gaps])

        bare_black_box = graph(spec("verify-1", relationship="black_box", covered_implementation_paths=[], dependencies=[]))
        self.assertIn("INSUFFICIENT_VERIFICATION_SCOPE", [gap.code for gap in bare_black_box.gaps])
        declared_black_box = graph(spec("verify-1", relationship="black_box", covered_implementation_paths=["src/**"], execution_scope=["tests/api/**"]))
        self.assertTrue(declared_black_box.is_structurally_valid, [gap.code for gap in declared_black_box.gaps])

        bare_external = graph(spec("verify-1", relationship="external_artifact", covered_implementation_paths=["src/**"], dependencies=[]))
        self.assertIn("INSUFFICIENT_VERIFICATION_SCOPE", [gap.code for gap in bare_external.gaps])
        sourced_external = graph(spec("verify-1", relationship="external_artifact", dependencies=[ref("verify-upstream")]))
        self.assertTrue(sourced_external.is_structurally_valid, [gap.code for gap in sourced_external.gaps])

        unpredicated = graph(spec("verify-1", relationship="human_approval"))
        self.assertIn("HUMAN_APPROVAL_WITHOUT_PREDICATE", [gap.code for gap in unpredicated.gaps])
        predicated = graph(spec("verify-1", relationship="human_approval", approval_predicate={"predicate_id": "signoff", "policy_digest": "a" * 64}))
        self.assertTrue(predicated.is_structurally_valid, [gap.code for gap in predicated.gaps])
