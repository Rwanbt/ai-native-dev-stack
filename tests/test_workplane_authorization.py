import unittest
from datetime import datetime, timedelta, timezone

from ainative_workplane.authorization import apply_authorizations
from ainative_workplane.contracts import generate_uid
from ainative_workplane.convergence import converge
from ainative_workplane.freshness import FreshnessResult
from ainative_workplane.traceability import Gap, analyze
from ainative_workplane.trust import TrustVerdict, policy_commitment

DIGEST = "a" * 64
NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def build_policy():
    policy = {
        "schema_name": "project_policy", "schema_version": 1,
        "approval_predicate": {"predicate_id": "review", "policy_digest": DIGEST},
        "success_condition_mutation_provenance": "GIT_REVIEWED",
        "verification_evidence_provenance": "GIT_REVIEWED",
        "waiver_approval_rule": {"predicate_id": "waiver-board", "policy_digest": DIGEST},
        "human_approval_rule": {"predicate_id": "human-signoff", "policy_digest": DIGEST},
        "promotion_policy": "explicit",
    }
    commitment = policy_commitment(policy)
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        policy[field]["policy_digest"] = commitment
    return policy, commitment


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.commitment = build_policy()
        self.target = generate_uid("task")
        self.gap = Gap("TASK_WITHOUT_VERIFICATION", self.target, "task has no requirement with verification")

    def waiver(self, **overrides):
        record = {
            "schema_name": "waiver", "schema_version": 1, "uid": generate_uid("waiver"),
            "target": {"uid": self.target, "digest": DIGEST},
            "reason": "accepted for this release", "scope": "TASK_WITHOUT_VERIFICATION",
            "approved_by": "release-board", "approved_at": "2026-09-01T00:00:00Z",
            "state": "effective", "approval_provenance": "GIT_REVIEWED",
            "approval_predicate": {"predicate_id": "waiver-board", "policy_digest": self.commitment},
            "policy_digest": self.commitment,
        }
        record.update(overrides)
        return record

    def approval(self, target, **overrides):
        record = {
            "schema_name": "human_approval", "schema_version": 1, "uid": generate_uid("approval"),
            "target": {"uid": target, "digest": DIGEST},
            "approved_by": "tech-lead", "approved_at": "2026-09-01T00:00:00Z",
            "approval_provenance": "GIT_REVIEWED",
            "approval_predicate": {"predicate_id": "human-signoff", "policy_digest": self.commitment},
            "policy_digest": self.commitment,
        }
        record.update(overrides)
        return record

    def codes(self, gaps):
        return [gap.code for gap in gaps]

    def apply(self, **kwargs):
        return apply_authorizations([self.gap], policy=self.policy, now=NOW, **kwargs)

    def test_authorized_effective_waiver_suppresses_only_its_target(self):
        self.assertEqual([], self.apply(waivers=[self.waiver()]))
        other = Gap("TASK_WITHOUT_VERIFICATION", generate_uid("task"), "another task")
        kept = apply_authorizations([self.gap, other], policy=self.policy, waivers=[self.waiver()], now=NOW)
        self.assertEqual([other], kept)
        wrong_scope = self.waiver(scope="REQ_WITHOUT_TASK")
        self.assertEqual(["TASK_WITHOUT_VERIFICATION"], self.codes(self.apply(waivers=[wrong_scope])))

    def test_proposed_and_expired_waivers_do_nothing(self):
        proposed = self.codes(self.apply(waivers=[self.waiver(state="proposed")]))
        self.assertIn("TASK_WITHOUT_VERIFICATION", proposed)
        self.assertIn("WAIVER_NOT_EFFECTIVE", proposed)
        past = (NOW - timedelta(days=1)).isoformat()
        expired = self.codes(self.apply(waivers=[self.waiver(expires_at=past)]))
        self.assertIn("TASK_WITHOUT_VERIFICATION", expired)
        self.assertIn("WAIVER_EXPIRED", expired)
        future = (NOW + timedelta(days=1)).isoformat()
        self.assertEqual([], self.apply(waivers=[self.waiver(expires_at=future)]))

    def test_self_approved_and_under_provenanced_waivers_are_rejected(self):
        self_approved = self.waiver(approval_predicate={"predicate_id": "its-own-rule", "policy_digest": self.commitment})
        rejected = self.codes(self.apply(waivers=[self_approved]))
        self.assertIn("TASK_WITHOUT_VERIFICATION", rejected)
        self.assertIn("UNAUTHORIZED_WAIVER", rejected)
        weak = self.waiver(approval_provenance="GIT_RECORDED")
        self.assertIn("UNAUTHORIZED_WAIVER", self.codes(self.apply(waivers=[weak])))
        stale_policy = self.waiver(policy_digest="b" * 64)
        self.assertIn("UNAUTHORIZED_WAIVER", self.codes(self.apply(waivers=[stale_policy])))
        malformed = self.waiver()
        del malformed["reason"]
        self.assertIn("INVALID_WAIVER", self.codes(self.apply(waivers=[malformed])))
        self.assertIn("UNAUTHORIZED_WAIVER", self.codes(apply_authorizations([self.gap], policy=None, waivers=[self.waiver()], now=NOW)))

    def test_no_waiver_can_suppress_an_unevaluable_gap(self):
        for code in ("ROOT_OF_TRUST_INVALID", "FRESHNESS_UNAVAILABLE", "INVALID_VERIFICATION_EVIDENCE", "UNRELATED_VERIFICATION_EVIDENCE"):
            gap = Gap(code, self.target, "authority could not be established")
            kept = apply_authorizations([gap], policy=self.policy, waivers=[self.waiver(scope=code)], now=NOW)
            self.assertIn(code, self.codes(kept), f"{code} must never be waivable")

    def test_human_approval_satisfies_a_specification_only_under_its_policy_predicate(self):
        specification = generate_uid("verify")
        gap = Gap("UNVERIFIED_SPECIFICATION", specification, "declared verification specification has no passing evidence")
        self.assertEqual([], apply_authorizations([gap], policy=self.policy, human_approvals=[self.approval(specification)], now=NOW))
        unconfigured = self.approval(specification, approval_predicate={"predicate_id": "not-in-policy", "policy_digest": self.commitment})
        rejected = self.codes(apply_authorizations([gap], policy=self.policy, human_approvals=[unconfigured], now=NOW))
        self.assertIn("UNVERIFIED_SPECIFICATION", rejected)
        self.assertIn("UNAUTHORIZED_HUMAN_APPROVAL", rejected)
        other_gap = Gap("VERIFICATION_FAILED", specification, "selected verification did not pass")
        self.assertIn("VERIFICATION_FAILED", self.codes(apply_authorizations([other_gap], policy=self.policy, human_approvals=[self.approval(specification)], now=NOW)))

    def test_converge_rejects_an_unauthorized_waiver_as_invalid(self):
        specification = generate_uid("verify")
        graph = analyze(
            [{"uid": "req-1", "acceptance_criteria": [{"uid": "ac-1", "digest": DIGEST}]}],
            [{"uid": "ac-1", "requirement": {"uid": "req-1", "digest": DIGEST}, "verification_specifications": [{"uid": specification, "digest": DIGEST}]}],
            [{"uid": "task-1", "requirements": [{"uid": "req-1", "digest": DIGEST}]}],
            [{"uid": specification}],
        )
        fresh = FreshnessResult(frozenset())
        trusted = TrustVerdict(True, "TRUSTED")
        self.assertEqual("NOT_CONVERGED", converge(graph, [], freshness=fresh, trust=trusted).verdict)

        forged = self.waiver(target={"uid": specification, "digest": DIGEST}, scope="UNVERIFIED_SPECIFICATION", approval_predicate={"predicate_id": "self", "policy_digest": self.commitment})
        verdict = converge(graph, [], freshness=fresh, trust=trusted, policy=self.policy, waivers=[forged])
        self.assertEqual("INVALID", verdict.verdict)
        self.assertIn("UNAUTHORIZED_WAIVER", self.codes(verdict.gaps))

        authorized = self.waiver(target={"uid": specification, "digest": DIGEST}, scope="UNVERIFIED_SPECIFICATION")
        covered = converge(graph, [], freshness=fresh, trust=trusted, policy=self.policy, waivers=[authorized])
        self.assertEqual("NOT_CONVERGED", covered.verdict)
        self.assertNotIn("UNVERIFIED_SPECIFICATION", self.codes(covered.gaps))
        self.assertIn("NO_VERIFICATION_EVIDENCE", self.codes(covered.gaps))


if __name__ == "__main__":
    unittest.main()
