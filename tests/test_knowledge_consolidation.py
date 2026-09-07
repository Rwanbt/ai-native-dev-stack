"""K7 gates: advisory consolidation changes nothing."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import consolidation as consolidationlib
from ainative.knowledge import evidence as evidencelib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib
from ainative.knowledge.candidate import capture
from tests.lifecycle_support import LifecycleTestCase


def _live(project: Path, claim: str, kind: str = "PROJECT_RULE",
          status: str = "CLASSIFIED") -> str:
    stored = storelib.append(project, capture(
        project=str(project), agent="opencode", session="sess-1",
        origin_type="user_correction", kind=kind, claim=claim))
    if status != "PENDING":
        reviewlib.classify_candidate(project, stored["candidate_id"], kind=kind,
                                     actor="tester")
    if status in ("SUPPORTED", "READY_FOR_PROMOTION"):
        evidencelib.add_evidence(project, stored["candidate_id"],
                                 {"type": "USER_CONFIRMATION", "locator": "s"},
                                 actor="tester")
        reviewlib.verify_candidate(project, stored["candidate_id"], actor="tester")
    if status == "READY_FOR_PROMOTION":
        storelib.set_status(project, stored["candidate_id"], status, actor="tester")
    return stored["candidate_id"]


def _snapshot(project: Path) -> list:
    return [(item["candidate_id"], item["status"], len(item["evidence"]))
            for item in storelib.read_all(project)]


class ConsolidationTest(unittest.TestCase):
    def test_Cluster_GroupsDuplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            first = _live(project, "Never mock the database.")
            second = _live(project, "NEVER mock the database!")
            _live(project, "Knobs are blue.")
            clusters = consolidationlib.cluster(storelib.read_all(project))
            self.assertEqual(len(clusters), 1)
            self.assertEqual(sorted(clusters[0]["members"]), sorted([first, second]))

    def test_Recommend_SupportedClean_SuggestsAdd(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            identifier = _live(project, "A lonely supported rule.", status="SUPPORTED")
            report = consolidationlib.consolidate(project)
            proposal = next(item for item in report["recommendations"]
                            if item["candidate_id"] == identifier)
            self.assertEqual(proposal["recommendation"], "ADD")

    def test_Recommend_DuplicatePair_SuggestsMerge(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _live(project, "Never mock the database.")
            second = _live(project, "NEVER mock the database!")
            report = consolidationlib.consolidate(project)
            proposal = next(item for item in report["recommendations"]
                            if item["candidate_id"] == second)
            self.assertEqual(proposal["recommendation"], "MERGE")

    def test_Recommend_Ambiguity_NeedsHuman(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _live(project, "Retry policy must be explicit per payment module.")
            second = _live(project, "Retry policy must be explicit per billing module.")
            report = consolidationlib.consolidate(project)
            proposal = next(item for item in report["recommendations"]
                            if item["candidate_id"] == second)
            self.assertEqual(proposal["recommendation"], "NEEDS_HUMAN")

    def test_Recommend_Pending_NeedsHuman(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            identifier = _live(project, "Unsorted thought.", status="PENDING")
            report = consolidationlib.consolidate(project)
            proposal = next(item for item in report["recommendations"]
                            if item["candidate_id"] == identifier)
            self.assertEqual(proposal["recommendation"], "NEEDS_HUMAN")

    def test_Consolidate_WritesNothing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _live(project, "Never mock the database.")
            _live(project, "NEVER mock the database!")
            _live(project, "A lonely supported rule.", status="SUPPORTED")
            before = _snapshot(project)
            audits_before = len(storelib.read_audit(project))
            consolidationlib.consolidate(project)
            self.assertEqual(_snapshot(project), before)
            self.assertEqual(len(storelib.read_audit(project)), audits_before)


class ConsolidateCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def test_Consolidate_AdvisoryJson(self):
        self.knowledge("capture", "--kind", "PROJECT_RULE",
                       "--claim", "Retries need explicit budgets.")
        completed = self.knowledge("consolidate", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertIn("recommendations", payload)
        self.assertIn("clusters", payload)
        self.assertTrue(any(item["recommendation"] == "NEEDS_HUMAN"
                            for item in payload["recommendations"]))


if __name__ == "__main__":
    unittest.main()