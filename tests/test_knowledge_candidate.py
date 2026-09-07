"""K1 gates: candidate contract, state machine, secrets, locators, store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import candidate as candidatelib
from ainative.knowledge import store as storelib
from ainative.knowledge.errors import KnowledgeError


def _pending(**overrides):
    record = candidatelib.capture(
        project="demo", agent="opencode", session="sess-1",
        origin_type="user_correction", kind="PROJECT_RULE",
        claim="Integration tests must use the real test database.")
    record.update(overrides)
    return candidatelib.validate_candidate(record)


class CaptureTest(unittest.TestCase):
    def test_Capture_ValidInput_YieldsPendingCandidate(self):
        record = _pending()
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["status"], "PENDING")
        self.assertEqual(record["target_hint"], "AGENTS.md")
        self.assertTrue(candidatelib.CANDIDATE_ID.match(record["candidate_id"]))

    def test_Capture_UnknownKind_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            _pending(kind="NOPE")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_Capture_EmptyClaim_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.capture(project="demo", agent="opencode", session="s",
                                 origin_type="manual", kind="PROJECT_RULE", claim="  ")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_Capture_NewerSchema_Refused(self):
        record = _pending()
        record["schema_version"] = 999
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.validate_candidate(record)
        self.assertEqual(caught.exception.code, "KNOWLEDGE_SCHEMA_UNKNOWN")


class TransitionTest(unittest.TestCase):
    def test_Transition_PendingToClassified_Allowed(self):
        updated = candidatelib.transition(_pending(), "CLASSIFIED")
        self.assertEqual(updated["status"], "CLASSIFIED")

    def test_Transition_PendingToPromoted_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.transition(_pending(), "PROMOTED")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_TRANSITION")

    def test_Transition_UnknownStatus_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.transition(_pending(), "ASCENDED")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_STATUS")

    def test_Transition_TerminalState_Frozen(self):
        record = _pending()
        record["status"] = "REJECTED"
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.transition(record, "SUPPORTED")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_TRANSITION")


class SecretLocatorTest(unittest.TestCase):
    def test_Secrets_ApiKeyInClaim_RefusedBeforePersistence(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.capture(project="demo", agent="opencode", session="s",
                                 origin_type="manual", kind="PROJECT_RULE",
                                 claim="Set api_key = abc123XYZ to deploy")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REJECTED")

    def test_Secrets_PrivateKeyInClaim_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.capture(project="demo", agent="opencode", session="s",
                                 origin_type="manual", kind="PROJECT_RULE",
                                 claim="-----BEGIN PRIVATE KEY-----")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REJECTED")

    def test_Secrets_TokenInProvenance_Refused(self):
        record = _pending()
        record["provenance"]["session"] = "sess auth_token = abc123"
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.validate_candidate(record)
        self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REJECTED")

    def test_Locator_AbsolutePath_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.validate_locator("/etc/passwd")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_LOCATOR")

    def test_Locator_Traversal_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            candidatelib.validate_locator("../../escape.md")
        self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_LOCATOR")

    def test_Locator_RepoRelative_Accepted(self):
        self.assertEqual(candidatelib.validate_locator("src/auth/token.ts"),
                         "src/auth/token.ts")


class StoreTest(unittest.TestCase):
    def test_Store_AppendThenInspect_RoundTrips(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = storelib.append(project, _pending())
            self.assertEqual(storelib.inspect_candidate(project, stored["candidate_id"]),
                             stored)

    def test_Store_DuplicateId_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = storelib.append(project, _pending())
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append(project, stored)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_DUPLICATE_ID")

    def test_Store_SetStatusIllegalTransition_RefusedAndUnchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = storelib.append(project, _pending())
            with self.assertRaises(KnowledgeError):
                storelib.set_status(project, stored["candidate_id"], "PROMOTED",
                                    actor="tester")
            self.assertEqual(
                storelib.inspect_candidate(project, stored["candidate_id"])["status"],
                "PENDING")

    def test_Store_SetStatusLegalTransition_Audited(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = storelib.append(project, _pending())
            updated = storelib.set_status(project, stored["candidate_id"],
                                          "CLASSIFIED", actor="tester")
            self.assertEqual(updated["status"], "CLASSIFIED")
            operations = [event["operation"] for event in storelib.read_audit(project)]
            self.assertIn("CAPTURE", operations)
            self.assertIn("TRANSITION", operations)

    def test_Store_SequentialWrites_BothSurvive(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            first = storelib.append(project, _pending())
            second = storelib.append(project, _pending())
            identifiers = {item["candidate_id"] for item in storelib.read_all(project)}
            self.assertEqual(identifiers, {first["candidate_id"], second["candidate_id"]})


if __name__ == "__main__":
    unittest.main()