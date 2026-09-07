"""PR2: B1 state vocabulary, legality, gating (B1 S5)."""

from __future__ import annotations

import unittest

from ainative.knowledge import states as stateslib
from ainative.knowledge.errors import KnowledgeError


class StatesTest(unittest.TestCase):
    def test_Vocabulary_HasFourteenStates(self):
        self.assertEqual(len(stateslib.STATES), 14)

    def test_HappyPath_PendingToReviewable(self):
        state = "PENDING"
        for target in ("IDENTITY_UNCONFIRMED", "NEEDS_SUPPORT", "REVIEWABLE"):
            state = stateslib.transition(state, target)
        self.assertEqual(state, "REVIEWABLE")

    def test_Skips_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            stateslib.transition("PENDING", "REVIEWABLE")
        self.assertEqual(caught.exception.code,
                         "KNOWLEDGE_ILLEGAL_STATE_TRANSITION")

    def test_UnknownStates_Refused(self):
        with self.assertRaises(KnowledgeError):
            stateslib.transition("PENDING", "ASCENDED")
        with self.assertRaises(KnowledgeError):
            stateslib.transition("LIMBO", "PENDING")

    def test_MutationTargets_GateClosed(self):
        for target in ("APPROVED", "PROMOTION_IN_PROGRESS",
                       "APPLIED_PENDING_COMMIT", "PROMOTED",
                       "PROMOTION_FAILED", "SUPERSEDED"):
            with self.subTest(target=target):
                with self.assertRaises(KnowledgeError) as caught:
                    stateslib.transition("REVIEWABLE", target)
                self.assertEqual(caught.exception.code, "KNOWLEDGE_GATE_CLOSED")

    def test_Terminal_HasNoExit(self):
        for state in ("REJECTED", "RETRACTED", "PROMOTED"):
            with self.subTest(state=state):
                self.assertTrue(stateslib.is_terminal(state))
                with self.assertRaises(KnowledgeError):
                    stateslib.transition(state, "REVIEWABLE")

    def test_NoSetterExists(self):
        exposed = [name for name in dir(stateslib)
                   if "set" in name.lower() and not name.startswith("_")]
        self.assertEqual(exposed, [])


if __name__ == "__main__":
    unittest.main()