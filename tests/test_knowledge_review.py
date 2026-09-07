"""K3 gates: evidence reinforcement, exact dedupe, conflicts, review."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import evidence as evidencelib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib
from ainative.knowledge.candidate import capture
from ainative.knowledge.classifier import suggest
from ainative.knowledge.dedupe import classify_pair, normalize, token_overlap
from ainative.knowledge.errors import KnowledgeError
from tests.lifecycle_support import LifecycleTestCase


def _pending(project: Path, claim: str = "Integration tests use the real database.",
             kind: str = "PROJECT_RULE") -> dict:
    return storelib.append(project, capture(
        project=str(project), agent="opencode", session="sess-1",
        origin_type="user_correction", kind=kind, claim=claim))


def _classified(project: Path, claim: str = "Integration tests use the real database.",
                kind: str = "PROJECT_RULE") -> dict:
    stored = _pending(project, claim, kind)
    return reviewlib.classify_candidate(project, stored["candidate_id"], kind=kind,
                                        actor="tester")


class EvidenceTest(unittest.TestCase):
    def test_Evidence_Append_ReinforcesWithoutDuplicating(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            updated, added = evidencelib.add_evidence(
                project, stored["candidate_id"],
                {"type": "TEST", "locator": "tests/test_db.py"}, actor="tester")
            self.assertTrue(added)
            self.assertEqual(len(updated["evidence"]), 1)
            same, added_again = evidencelib.add_evidence(
                project, stored["candidate_id"],
                {"type": "TEST", "locator": "tests/test_db.py"}, actor="tester")
            self.assertFalse(added_again)
            self.assertEqual(len(same["evidence"]), 1)

    def test_Evidence_OnTerminal_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            storelib.set_status(project, stored["candidate_id"], "REJECTED",
                                actor="tester")
            with self.assertRaises(KnowledgeError) as caught:
                evidencelib.add_evidence(project, stored["candidate_id"],
                                         {"type": "TEST", "locator": "x.py"})
            self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_TRANSITION")

    def test_Evidence_SecretLocator_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            with self.assertRaises(KnowledgeError) as caught:
                evidencelib.add_evidence(project, stored["candidate_id"],
                                         {"type": "TEST", "locator": "api_key = abc"})
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REJECTED")

    def test_Evidence_SecretInAnyField_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            with self.assertRaises(KnowledgeError) as caught:
                evidencelib.add_evidence(project, stored["candidate_id"],
                                         {"type": "TEST", "locator": "x.py",
                                          "repository_state": "auth_token = abc123"})
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REJECTED")

    def test_Sufficiency_Rules(self):
        self.assertEqual(evidencelib.sufficiency([])[0], False)
        weak = [{"type": "REPEATED_OBSERVATION"}]
        self.assertEqual(evidencelib.sufficiency(weak)[0], False)
        self.assertEqual(evidencelib.sufficiency(weak * 2)[0], False)
        strong = [{"type": "USER_CONFIRMATION"}]
        self.assertEqual(evidencelib.sufficiency(strong)[0], True)


class DedupeTest(unittest.TestCase):
    def test_Normalize_IgnoresCaseAndPunctuation(self):
        self.assertEqual(normalize("  Must, NEVER mock!  "), "must never mock")

    def test_ClassifyPair_Identical_IsDuplicate(self):
        relation, _, _ = classify_pair("Must never mock the DB.", "AGENTS.md",
                                       "must NEVER mock the db!", "AGENTS.md")
        self.assertEqual(relation, "DUPLICATE")

    def test_ClassifyPair_Containment_IsRefinement(self):
        relation, _, explanation = classify_pair(
            "Never mock.", "AGENTS.md",
            "Never mock the database in integration tests.", "AGENTS.md")
        self.assertEqual(relation, "REFINEMENT")
        self.assertIn("contained", explanation)

    def test_ClassifyPair_OverlapSameTarget_IsConflict(self):
        relation, score, _ = classify_pair(
            "Retry policy must be explicit per payment module.", "AGENTS.md",
            "Retry policy must be explicit per billing module.", "AGENTS.md")
        self.assertEqual(relation, "CONFLICTS")
        self.assertGreaterEqual(score, 0.6)

    def test_ClassifyPair_Unrelated_StaysUnrelated(self):
        relation, _, _ = classify_pair("Use the real database.", "AGENTS.md",
                                       "Knobs are blue in dark mode.", "AGENTS.md")
        self.assertEqual(relation, "UNRELATED")

    def test_TokenOverlap_Empty_IsZero(self):
        self.assertEqual(token_overlap("", "something"), 0.0)


class ClassifierTest(unittest.TestCase):
    def test_Suggest_FailureVocabulary(self):
        self.assertEqual(suggest("Flaky test crashes CI")["kind"], "FAILURE_PATTERN")

    def test_Suggest_ModuleNamesInvariant(self):
        result = suggest("Timeouts confuse the runner", module="vault")
        self.assertEqual(result["kind"], "MODULE_INVARIANT")

    def test_Suggest_UnknownWhenNothingMatches(self):
        result = suggest("Knobs are blue in dark mode")
        self.assertEqual(result["kind"], "UNKNOWN")
        self.assertTrue(result["reasons"])


class ReviewTest(unittest.TestCase):
    def test_Classify_SetsKindAndStatus(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _pending(project, kind="UNKNOWN")
            updated = reviewlib.classify_candidate(project, stored["candidate_id"],
                                                   kind="PROJECT_RULE", actor="tester")
            self.assertEqual((updated["status"], updated["kind"]),
                             ("CLASSIFIED", "PROJECT_RULE"))

    def test_Classify_FromNonPending_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            with self.assertRaises(KnowledgeError) as caught:
                reviewlib.classify_candidate(project, stored["candidate_id"])
            self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_TRANSITION")

    def test_Verify_NoEvidence_NeedsEvidence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            report = reviewlib.verify_candidate(project, stored["candidate_id"],
                                                actor="tester")
            self.assertEqual((report["from"], report["to"]),
                             ("CLASSIFIED", "NEEDS_EVIDENCE"))

    def test_Verify_StrongEvidence_SupportedViaAuditedHops(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _classified(project)
            evidencelib.add_evidence(project, stored["candidate_id"],
                                     {"type": "USER_CONFIRMATION",
                                      "locator": "session notes"}, actor="tester")
            report = reviewlib.verify_candidate(project, stored["candidate_id"],
                                                actor="tester")
            self.assertEqual(report["to"], "SUPPORTED")
            self.assertEqual(report["hops"], ["NEEDS_EVIDENCE", "SUPPORTED"])

    def test_Verify_ExactDuplicate_MarksDuplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            first = _classified(project)
            second = _classified(project)
            report = reviewlib.verify_candidate(project, second["candidate_id"],
                                                actor="tester")
            self.assertEqual(report["to"], "DUPLICATE")
            self.assertTrue(any(item["class"] == "DUPLICATE_CONFLICT"
                                for item in report["findings"]))
            self.assertEqual(storelib.inspect_candidate(
                project, first["candidate_id"])["status"], "CLASSIFIED")

    def test_Verify_CanonicalVerbatim_MarksDuplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "AGENTS.md").write_text(
                "# Rules\n\nIntegration tests use the real database.\n",
                encoding="utf-8")
            stored = _classified(project)
            report = reviewlib.verify_candidate(project, stored["candidate_id"],
                                                actor="tester")
            self.assertEqual(report["to"], "DUPLICATE")
            self.assertTrue(any(item["with"] == "AGENTS.md" for item in report["findings"]))

    def test_Verify_Ambiguity_ConflictsWithoutCanonicalWrite(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _classified(project, "Retry policy must be explicit per payment module.")
            second = _classified(project, "Retry policy must be explicit per billing module.")
            report = reviewlib.verify_candidate(project, second["candidate_id"],
                                                actor="tester")
            self.assertEqual(report["to"], "CONFLICTING")
            self.assertTrue(any(item["class"] == "SEMANTIC_AMBIGUITY"
                                for item in report["findings"]))
            self.assertFalse((project / "AGENTS.md").exists())

    def test_Verify_FromPending_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = _pending(project)
            with self.assertRaises(KnowledgeError) as caught:
                reviewlib.verify_candidate(project, stored["candidate_id"])
            self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_TRANSITION")


class ReviewCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def test_ReviewFlow_EndToEnd_ThroughCli(self):
        captured = self.knowledge("capture", "--kind", "PROJECT_RULE",
                                  "--claim", "Retries need explicit budgets.",
                                  "--json")
        identifier = json.loads(captured.stdout)["candidate_id"]
        preview = self.knowledge("classify", identifier, "--dry-run", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        json.loads(preview.stdout)
        classified = self.knowledge("classify", identifier, "--json")
        self.assertEqual(classified.returncode, 0, classified.stderr)
        first = self.knowledge("verify", identifier, "--json")
        self.assertEqual(json.loads(first.stdout)["to"], "NEEDS_EVIDENCE")
        evidenced = self.knowledge("evidence", identifier, "--type", "TEST",
                                   "--locator", "tests/test_retry.py", "--json")
        self.assertEqual(evidenced.returncode, 0, evidenced.stderr)
        second = self.knowledge("verify", identifier, "--json")
        payload = json.loads(second.stdout)
        self.assertEqual(payload["to"], "SUPPORTED")
        self.assertEqual(payload["hops"], ["SUPPORTED"])

    def test_ReviewCommands_EmitParseableJson(self):
        captured = self.knowledge("capture", "--kind", "UNKNOWN",
                                  "--claim", "Something unclear.", "--json")
        identifier = json.loads(captured.stdout)["candidate_id"]
        preview = self.knowledge("classify", identifier, "--dry-run", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        json.loads(preview.stdout)
        classified = self.knowledge("classify", identifier, "--json")
        self.assertEqual(classified.returncode, 0, classified.stderr)
        for command in (("evidence", identifier, "--type", "TEST",
                         "--locator", "x.py", "--dry-run", "--json"),
                        ("verify", identifier, "--dry-run", "--json")):
            with self.subTest(command=command[0]):
                completed = self.knowledge(*command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                try:
                    json.loads(completed.stdout)
                except ValueError:
                    self.fail(f"{command} did not emit JSON:\n{completed.stdout[:400]}")


if __name__ == "__main__":
    unittest.main()