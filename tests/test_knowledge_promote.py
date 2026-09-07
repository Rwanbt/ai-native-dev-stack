"""K4b gates: approval policy and the promote/reject/reconcile CLI."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import policy as policylib
from ainative.knowledge import promotion as promotionlib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib
from ainative.knowledge import evidence as evidencelib
from ainative.knowledge.candidate import capture
from ainative.knowledge.errors import KnowledgeError
from tests.lifecycle_support import LifecycleTestCase


def _ready(project: Path, claim: str = "Integration tests use the real database.",
           kind: str = "PROJECT_RULE") -> dict:
    stored = storelib.append(project, capture(
        project=str(project), agent="opencode", session="sess-1",
        origin_type="user_correction", kind=kind, claim=claim))
    reviewlib.classify_candidate(project, stored["candidate_id"], kind=kind,
                                 actor="tester")
    evidencelib.add_evidence(project, stored["candidate_id"],
                             {"type": "USER_CONFIRMATION", "locator": "session"},
                             actor="tester")
    reviewlib.verify_candidate(project, stored["candidate_id"], actor="tester")
    return storelib.set_status(project, stored["candidate_id"],
                               "READY_FOR_PROMOTION", actor="tester")


def _write(project: Path, relative: str, content: str) -> Path:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


class PolicyTest(unittest.TestCase):
    def test_Policy_AgentsMd_NeedsHuman(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _ready(project)
            dest = project / "AGENTS.md"
            with self.assertRaises(KnowledgeError) as caught:
                policylib.check(project, stored, dest, actor="agent", approve=None)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_APPROVAL_REQUIRED")
            approval = policylib.check(project, stored, dest, actor="lead",
                                       approve="accepted")
            self.assertEqual(approval["target_class"], "AGENTS.md")

    def test_Policy_OtherTarget_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "notes.md", "# Notes\n")
            stored = _ready(project)
            with self.assertRaises(KnowledgeError) as caught:
                policylib.check(project, stored, project / "notes.md",
                                actor="lead", approve="yes")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_TARGET_UNSUPPORTED")

    def test_Policy_ClassifyAdr(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            dest = project / "docs" / "adr" / "0001-x.md"
            self.assertEqual(policylib.classify_target(project, dest), "ADR")


class PromoteCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def _ready_id(self, claim: str = "Retries need explicit budgets.") -> str:
        captured = self.knowledge("capture", "--kind", "PROJECT_RULE",
                                  "--claim", claim, "--json")
        identifier = json.loads(captured.stdout)["candidate_id"]
        self.knowledge("classify", identifier)
        self.knowledge("evidence", identifier, "--type", "TEST",
                       "--locator", "tests/test_retry.py")
        self.knowledge("verify", identifier)
        moved = self.knowledge("transition", identifier, "READY_FOR_PROMOTION",
                               "--actor", "lead")
        self.assertEqual(moved.returncode, 0, moved.stderr)
        return identifier

    def _seed_agents(self) -> None:
        (self.project / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")

    def test_Promote_WithoutApproval_RefusedWithoutWriting(self):
        self._seed_agents()
        identifier = self._ready_id()
        refused = self.knowledge("promote", identifier, "--operation", "ADD",
                                 "--expect-base", "0" * 64)
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("KNOWLEDGE_APPROVAL_REQUIRED", refused.stderr)
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"),
                         "# Rules\n")

    def test_Promote_WithoutBase_Refused(self):
        self._seed_agents()
        identifier = self._ready_id()
        refused = self.knowledge("promote", identifier, "--operation", "ADD",
                                 "--approve", "yes")
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("preview-first", refused.stderr)

    def test_Promote_FullFlow_PatchesAndPromotes(self):
        self._seed_agents()
        identifier = self._ready_id()
        preview = self.knowledge("promote", identifier, "--operation", "ADD",
                                 "--dry-run", "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        base = json.loads(preview.stdout)["base_digest"]
        done = self.knowledge("promote", identifier, "--operation", "ADD",
                              "--approve", "accepted in review",
                              "--expect-base", base, "--actor", "lead", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        body = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Retries need explicit budgets.", body)
        inspected = self.knowledge("inspect", identifier, "--json")
        self.assertEqual(json.loads(inspected.stdout)["status"], "PROMOTED")
        operations = [event["operation"] for event in
                      storelib.read_audit(self.project)]
        self.assertIn("APPROVE", operations)
        self.assertIn("PROMOTE", operations)

    def test_Reject_MovesToRejectedWithoutWriting(self):
        self._seed_agents()
        identifier = self._ready_id()
        rejected = self.knowledge("reject", identifier, "--actor", "lead")
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"),
                         "# Rules\n")

    def test_Reconcile_Consistent_Project(self):
        self._seed_agents()
        identifier = self._ready_id()
        preview = self.knowledge("promote", identifier, "--operation", "ADD",
                                 "--dry-run", "--json")
        base = json.loads(preview.stdout)["base_digest"]
        self.knowledge("promote", identifier, "--operation", "ADD",
                       "--approve", "yes", "--expect-base", base)
        reconciled = self.knowledge("reconcile", identifier, "--json")
        self.assertEqual(json.loads(reconciled.stdout)["state"], "consistent")

    def test_PromoteCommands_EmitParseableJson(self):
        self._seed_agents()
        identifier = self._ready_id()
        preview = self.knowledge("promote", identifier, "--operation", "ADD",
                                 "--dry-run", "--json")
        base = json.loads(preview.stdout)["base_digest"]
        for command in (("reject", identifier, "--dry-run", "--json"),
                        ("reconcile", identifier, "--dry-run", "--json")):
            with self.subTest(command=command[0]):
                completed = self.knowledge(*command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                json.loads(completed.stdout)
        done = self.knowledge("promote", identifier, "--operation", "ADD",
                              "--approve", "yes", "--expect-base", base, "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        json.loads(done.stdout)


if __name__ == "__main__":
    unittest.main()