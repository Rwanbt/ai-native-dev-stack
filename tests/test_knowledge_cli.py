"""K1b gates: the `ainative knowledge` CLI contract and the layer boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from tests.lifecycle_support import LifecycleTestCase, REPO


class KnowledgeCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def capture_id(self, claim: str = "Integration tests use the real database.") -> str:
        completed = self.knowledge("capture", "--kind", "PROJECT_RULE",
                                   "--claim", claim, "--agent", "opencode",
                                   "--origin", "user_correction", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)["candidate_id"]

    def test_Status_EmptyStore_ReportsNoCandidates(self):
        completed = self.knowledge("status")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no candidates", completed.stdout)

    def test_Capture_ThenList_RoundTrips(self):
        identifier = self.capture_id()
        listed = self.knowledge("candidates", "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        identifiers = [item["candidate_id"] for item in json.loads(listed.stdout)["candidates"]]
        self.assertEqual(identifiers, [identifier])

    def test_Capture_DryRun_WritesNothing(self):
        completed = self.knowledge("capture", "--kind", "FAILURE_PATTERN",
                                   "--claim", "dry run only", "--dry-run")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse((self.project / ".ai-native" / "knowledge"
                          / "candidates.jsonl").exists())

    def test_Transition_IllegalMove_RefusedAndUnchanged(self):
        identifier = self.capture_id()
        refused = self.knowledge("transition", identifier, "PROMOTED")
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("KNOWLEDGE_BAD_TRANSITION", refused.stderr)
        inspected = self.knowledge("inspect", identifier, "--json")
        self.assertEqual(json.loads(inspected.stdout)["status"], "PENDING")

    def test_Transition_LegalMove_Persists(self):
        identifier = self.capture_id()
        moved = self.knowledge("transition", identifier, "classified", "--actor", "tester")
        self.assertEqual(moved.returncode, 0, moved.stderr)
        self.assertIn("CLASSIFIED", moved.stdout)

    def test_Capture_SecretClaim_RefusedBeforePersistence(self):
        refused = self.knowledge("capture", "--kind", "PROJECT_RULE",
                                 "--claim", "deploy with api_key = abc123XYZ")
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("KNOWLEDGE_SECRET_REJECTED", refused.stderr)
        self.assertFalse((self.project / ".ai-native" / "knowledge"
                          / "candidates.jsonl").exists())

    def test_EveryKnowledgeCommand_EmitsParseableJson(self):
        identifier = self.capture_id()
        for command in (("status", "--json"), ("candidates", "--json"),
                        ("inspect", identifier, "--json"),
                        ("capture", "--kind", "PROJECT_RULE", "--claim", "x",
                         "--dry-run", "--json"),
                        ("transition", identifier, "CLASSIFIED", "--dry-run", "--json")):
            with self.subTest(command=command):
                completed = self.knowledge(*command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                try:
                    json.loads(completed.stdout)
                except ValueError:
                    self.fail(f"{command} did not emit JSON:\n{completed.stdout[:400]}")

    def test_DoctorJson_CarriesKnowledgeSection(self):
        self.capture_id()
        completed = self.cli("doctor", "--json")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["knowledge"]["candidates"], 1)
        self.assertEqual(payload["knowledge"]["state"], "healthy")

    def test_KnowledgeLayer_NeverImportsTheWorkPlane(self):
        import os

        script = ("import sys\nimport ainative.cli, ainative.knowledge.candidate, "
                  "ainative.knowledge.store, ainative.knowledge.health\n"
                  "print('\\n'.join(sorted(m for m in sys.modules "
                  "if m.startswith('ainative'))))\n")
        completed = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                   text=True, cwd=str(REPO),
                                   env={**os.environ, "PYTHONPATH": str(REPO)})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        offenders = {name for name in completed.stdout.split()
                     if name.startswith("ainative_workplane")}
        self.assertEqual(offenders, set())


if __name__ == "__main__":
    unittest.main()