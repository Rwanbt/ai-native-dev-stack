"""K6 gates: change impact, review candidates, bridge, no auto-rewrite."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import evidence as evidencelib
from ainative.knowledge import promotion as promotionlib
from ainative.knowledge import providers as providerslib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import staleness as stalenesslib
from ainative.knowledge import store as storelib
from ainative.knowledge.candidate import capture
from tests.lifecycle_support import LifecycleTestCase


class FakeGraph:
    name = "fake-graph"

    def __init__(self, peers: dict) -> None:
        self.peers = peers

    def probe(self) -> str:
        return "available (fake)"

    def neighbors(self, path: str, *, max_neighbors: int = 10):
        return [providerslib.GraphNeighbor(path=peer, distance=1)
                for peer in self.peers.get(path, [])[:max_neighbors]]


def _write(project: Path, relative: str, content: str) -> Path:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _promoted(project: Path, claim: str = "Integration tests use the real database.",
              evidence: list | None = None) -> dict:
    stored = storelib.append(project, capture(
        project=str(project), agent="opencode", session="sess-1",
        origin_type="user_correction", kind="PROJECT_RULE", claim=claim))
    reviewlib.classify_candidate(project, stored["candidate_id"],
                                 kind="PROJECT_RULE", actor="tester")
    for item in evidence or []:
        evidencelib.add_evidence(project, stored["candidate_id"], item,
                                 actor="tester")
    evidencelib.add_evidence(project, stored["candidate_id"],
                             {"type": "USER_CONFIRMATION", "locator": "session"},
                             actor="tester")
    reviewlib.verify_candidate(project, stored["candidate_id"], actor="tester")
    storelib.set_status(project, stored["candidate_id"], "READY_FOR_PROMOTION",
                        actor="tester")
    promotionlib.apply_promotion(project, stored["candidate_id"],
                                 operation="ADD", actor="tester",
                                 expect_base=None)
    return storelib.inspect_candidate(project, stored["candidate_id"])


class ImpactTest(unittest.TestCase):
    def test_ChangedTarget_FlagsPotentiallyStale(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _promoted(project)
            findings = stalenesslib.impacted(project, ["AGENTS.md"])
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["state"], "POTENTIALLY_STALE")
            self.assertEqual(findings[0]["signals"][0]["signal"], "target-modified")
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "PROMOTED")

    def test_ChangedEvidencePath_Flags(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            _promoted(project, evidence=[{"type": "SOURCE_CODE",
                                          "locator": "src/db.py"}])
            findings = stalenesslib.impacted(project, ["src/db.py"])
            self.assertTrue(any(signal["signal"] == "evidence-path-modified"
                                for signal in findings[0]["signals"]))

    def test_GraphAdjacent_Flags(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _promoted(project)
            graph = FakeGraph({"src/db.py": ["AGENTS.md"]})
            findings = stalenesslib.impacted(project, ["src/db.py"], graph=graph)
            self.assertEqual(findings[0]["candidate_id"], stored["candidate_id"])
            self.assertTrue(any(signal["signal"] == "graph-adjacent"
                                for signal in findings[0]["signals"]))

    def test_RelocatedFile_Flags(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            _promoted(project, evidence=[{"type": "SOURCE_CODE",
                                          "locator": "src/old.py"}])
            findings = stalenesslib.impacted(project, ["lib/old.py"])
            self.assertTrue(any(signal["signal"] == "possibly-relocated"
                                for signal in findings[0]["signals"]))

    def test_UnrelatedChange_Empty(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            _promoted(project)
            self.assertEqual(stalenesslib.impacted(project, ["README.md"]), [])


class ReviewCandidatesTest(unittest.TestCase):
    def test_Apply_RaisesPendingWithGitEvidence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _promoted(project)
            findings = stalenesslib.impacted(project, ["AGENTS.md"])
            outcome = stalenesslib.raise_reviews(project, findings, actor="tester")
            self.assertEqual(len(outcome["created"]), 1)
            child = storelib.inspect_candidate(project, outcome["created"][0])
            self.assertEqual(child["status"], "PENDING")
            self.assertTrue(any(item["type"] == "GIT_HISTORY"
                                for item in child["evidence"]))
            audits = [event for event in storelib.read_audit(project)
                      if event["operation"] == "STALENESS_REVIEW"]
            self.assertEqual(audits[0]["detail"]["parent"], stored["candidate_id"])
            self.assertEqual(storelib.inspect_candidate(
                project, stored["candidate_id"])["status"], "PROMOTED")

    def test_Apply_Twice_DoesNotSpam(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            _promoted(project)
            findings = stalenesslib.impacted(project, ["AGENTS.md"])
            first = stalenesslib.raise_reviews(project, findings, actor="tester")
            second = stalenesslib.raise_reviews(project, findings, actor="tester")
            self.assertEqual(len(first["created"]), 1)
            self.assertEqual(second["created"], [])
            self.assertEqual(len(second["skipped"]), 1)

    def test_Bridge_MapsCodeToKnowledge(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "AGENTS.md", "# Rules\n")
            stored = _promoted(project)
            registry = stalenesslib.bridge(project)
            self.assertIn(stored["candidate_id"],
                          registry["code_index"].get("AGENTS.md", []))


class StaleCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def test_Stale_ReportAndApply_Json(self):
        (self.project / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        captured = self.knowledge("capture", "--kind", "PROJECT_RULE",
                                  "--claim", "Use the real database.", "--json")
        identifier = json.loads(captured.stdout)["candidate_id"]
        self.knowledge("classify", identifier)
        self.knowledge("evidence", identifier, "--type", "USER_CONFIRMATION",
                       "--locator", "session")
        self.knowledge("verify", identifier)
        self.knowledge("transition", identifier, "READY_FOR_PROMOTION")
        preview = self.knowledge("promote", identifier, "--operation", "ADD",
                                 "--dry-run", "--json")
        base = json.loads(preview.stdout)["base_digest"]
        promoted = self.knowledge("promote", identifier, "--operation", "ADD",
                                  "--approve", "yes", "--expect-base", base)
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        reported = self.knowledge("stale", "--changed", "AGENTS.md", "--json")
        self.assertEqual(reported.returncode, 0, reported.stderr)
        payload = json.loads(reported.stdout)
        self.assertEqual(len(payload["findings"]), 1)
        self.assertIn("AGENTS.md", payload["bridge"]["code_index"])
        applied = self.knowledge("stale", "--changed", "AGENTS.md", "--apply",
                                 "--json")
        result = json.loads(applied.stdout)["applied"]
        self.assertEqual(len(result["created"]), 1)
        again = self.knowledge("stale", "--changed", "AGENTS.md", "--apply",
                               "--json")
        self.assertEqual(json.loads(again.stdout)["applied"]["created"], [])


if __name__ == "__main__":
    unittest.main()