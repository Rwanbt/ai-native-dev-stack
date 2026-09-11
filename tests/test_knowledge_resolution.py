"""PR11 gates: normative order, confirmed-only conflict, prose blindness."""

from __future__ import annotations

import unittest

from ainative.knowledge import resolution as resolutionlib


def _record(identifier: str, key: str = "module/payment/retry/attempts",
            digest: str = "h1", claim: str = "Use retries.") -> dict:
    return {"candidate_id": identifier,
            "identity": {"identity_key": key,
                         "identity_key_grammar_version": 1},
            "assertion_hash": digest, "claim": claim}


class OrderTest(unittest.TestCase):
    def test_ConflictBeatsDuplicate(self):
        me = _record("me", digest="h1")
        rival = _record("rival", digest="h2")
        twin = _record("twin", digest="h1")
        verdict = resolutionlib.resolve(
            me, existing=[rival, twin], confirmed_identities={"module/payment/retry/attempts"})
        self.assertEqual(verdict["verdict"], "CONFLICT")

    def test_NoConflictNoDuplicate_IsUnique(self):
        verdict = resolutionlib.resolve(_record("me"), existing=[])
        self.assertEqual(verdict["verdict"], "UNIQUE")

    def test_ExactHash_IsDuplicate(self):
        verdict = resolutionlib.resolve(
            _record("me", digest="h9"),
            existing=[_record("holder", digest="h9")])
        self.assertEqual(verdict["verdict"], "DUPLICATE")
        self.assertEqual(verdict["holder"], "holder")

    def test_ChangedAssertion_StaysReviewable(self):
        verdict = resolutionlib.resolve(
            _record("me", digest="h2"),
            existing=[_record("old", digest="h1")])
        self.assertEqual(verdict["verdict"], "ADVISORY")
        self.assertNotIn(verdict["verdict"], ("REJECTED", "DUPLICATE"))


class TombstoneTest(unittest.TestCase):
    def test_PriorRejection_Recognized(self):
        verdict = resolutionlib.resolve(
            _record("me", digest="dead"), existing=[],
            tombstones={"dead"})
        self.assertEqual(verdict["verdict"], "TOMBSTONE")

    def test_ChangedAssertion_NotTombstoned(self):
        verdict = resolutionlib.resolve(
            _record("me", digest="fresh"), existing=[],
            tombstones={"dead"})
        self.assertEqual(verdict["verdict"], "UNIQUE")


class AdvisoryTest(unittest.TestCase):
    def test_UnconfirmedDivergence_IsAdvisory(self):
        verdict = resolutionlib.resolve(
            _record("me", digest="h2"),
            existing=[_record("other", digest="h1")],
            confirmed_identities=set())
        self.assertEqual(verdict["verdict"], "ADVISORY")

    def test_ConfirmedDivergence_IsConflict(self):
        verdict = resolutionlib.resolve(
            _record("me", digest="h2"),
            existing=[_record("other", digest="h1")],
            confirmed_identities={"module/payment/retry/attempts"})
        self.assertEqual(verdict["verdict"], "CONFLICT")
        self.assertEqual(verdict["holders"], ["other"])

    def test_ProseContradiction_Ignored(self):
        left = _record("a", key="module/payment/retry/attempts",
                       claim="Always retry.")
        right = _record("b", key="module/payment/timeout/limit",
                        claim="Never retry.")
        verdict = resolutionlib.resolve(left, existing=[right])
        self.assertEqual(verdict["verdict"], "UNIQUE")


class SupportTest(unittest.TestCase):
    def test_Support_CountsByKind(self):
        supports = [{"candidate_id": "me", "kind": "test"},
                    {"candidate_id": "me", "kind": "test"},
                    {"candidate_id": "me", "kind": "note"},
                    {"candidate_id": "other", "kind": "test"}]
        summary = resolutionlib.support_summary("me", supports)
        self.assertEqual(summary, {"candidate_id": "me", "total": 3,
                                   "by_kind": {"test": 2, "note": 1}})

    def test_Verdict_CarriesSupport(self):
        verdict = resolutionlib.resolve(
            _record("me"), existing=[],
            supports=[{"candidate_id": "me", "kind": "test"}])
        self.assertEqual(verdict["support"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
