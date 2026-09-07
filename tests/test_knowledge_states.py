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

    def test_IllegalBeatsGateClosed(self):
        with self.assertRaises(KnowledgeError) as caught:
            stateslib.transition("REJECTED", "APPROVED")
        self.assertEqual(caught.exception.code,
                         "KNOWLEDGE_ILLEGAL_STATE_TRANSITION")

    def test_MutationChain_EdgesExistButGateClosed(self):
        state = "REVIEWABLE"
        for target in ("APPROVED", "PROMOTION_IN_PROGRESS",
                       "APPLIED_PENDING_COMMIT", "PROMOTED"):
            with self.subTest(target=target):
                with self.assertRaises(KnowledgeError) as caught:
                    stateslib.transition(state, target)
                self.assertEqual(caught.exception.code, "KNOWLEDGE_GATE_CLOSED")
                state = target

    def test_GateClosed_ExitsFailedNotInvalid(self):
        from ainative.knowledge.errors import KnowledgeError as KError
        try:
            stateslib.transition("REVIEWABLE", "APPROVED")
        except KError as error:
            self.assertEqual(error.exit_code, 1)

    def test_ReviewableRow_ExactLegality(self):
        for target, code in (("APPROVED", "KNOWLEDGE_GATE_CLOSED"),
                             ("PROMOTION_IN_PROGRESS",
                              "KNOWLEDGE_ILLEGAL_STATE_TRANSITION"),
                             ("APPLIED_PENDING_COMMIT",
                              "KNOWLEDGE_ILLEGAL_STATE_TRANSITION"),
                             ("PROMOTED", "KNOWLEDGE_ILLEGAL_STATE_TRANSITION"),
                             ("PROMOTION_FAILED",
                              "KNOWLEDGE_ILLEGAL_STATE_TRANSITION"),
                             ("SUPERSEDED", "KNOWLEDGE_ILLEGAL_STATE_TRANSITION"),
                             ("CONFLICTING", None),
                             ("DUPLICATE", None)):
            with self.subTest(target=target):
                if code is None:
                    self.assertEqual(stateslib.transition("REVIEWABLE", target),
                                     target)
                else:
                    with self.assertRaises(KnowledgeError) as caught:
                        stateslib.transition("REVIEWABLE", target)
                    self.assertEqual(caught.exception.code, code)

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
