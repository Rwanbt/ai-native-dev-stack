"""Consolidation: advisory outcomes only, zero writes, resolution-owned order."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ainative.knowledge import assertions as assertionslib
from ainative.knowledge import consolidation as consolidationlib
from ainative.knowledge import identity as identitylib
from ainative.knowledge import imports as importslib
from ainative.knowledge import states as stateslib
from ainative.knowledge import store as storelib
from ainative.lifecycle import state as statelib


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "src.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _apply(project: Path, root: Path, slug: str, item: dict):
    source = root / "items.json"
    source.write_text(json.dumps([item]), encoding="utf-8")
    return importslib.apply(project, source, harness="claude", project_slug=slug)


class ConsolidationTests(unittest.TestCase):
    def test_unique_without_support_needs_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "consolidatesandbox"
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/review"})
            report = consolidationlib.consolidate(project)
            self.assertEqual(1, len(report["proposals"]))
            self.assertEqual(consolidationlib.NEEDS_EVIDENCE, report["proposals"][0]["outcome"])

    def test_unique_with_support_adds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "consolidatesandbox"
            applied = _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                                   "identity_key": f"project/{slug}/workflow/review"})
            target = applied["created"][0]
            with mock.patch.object(consolidationlib.storelib, "list_supports",
                                   return_value=[{"candidate_id": target, "kind": "test"}]):
                report = consolidationlib.consolidate(project)
            self.assertEqual(consolidationlib.ADD, report["proposals"][0]["outcome"])

    def test_duplicate_proposes_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "consolidatesandbox"
            item = {"claim": "workflow review happens on Fridays",
                    "identity_key": f"project/{slug}/workflow/review"}
            _apply(project, root, slug, item)
            _apply(project, root, slug, item)
            report = consolidationlib.consolidate(project)
            outcomes = [item["outcome"] for item in report["proposals"]]
            self.assertEqual(2, len(outcomes))
            self.assertTrue(all(outcome == consolidationlib.MERGE for outcome in outcomes))

    def test_conflict_proposes_needs_human(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "consolidatesandbox"
            key = f"project/{slug}/workflow/review"
            _apply(project, root, slug, {"claim": "review happens on Fridays", "identity_key": key})
            _apply(project, root, slug, {"claim": "review happens on Mondays", "identity_key": key})
            report = consolidationlib.consolidate(project)
            outcomes = [item["outcome"] for item in report["proposals"]]
            self.assertEqual(2, len(outcomes))
            self.assertTrue(all(outcome == consolidationlib.NEEDS_HUMAN for outcome in outcomes))

    def test_consolidate_writes_nothing_and_transitions_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "consolidatesandbox"
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/review"})
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            before_bytes = candidates.read_bytes()
            before_states = [item.get("state") for item in storelib.list_candidates(project)]
            first = consolidationlib.consolidate(project)
            second = consolidationlib.consolidate(project)
            self.assertEqual(first["proposals"], second["proposals"])
            self.assertEqual(before_bytes, candidates.read_bytes())
            self.assertEqual(before_states,
                             [item.get("state") for item in storelib.list_candidates(project)])

    def test_dependency_metadata_enriches_proposals(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "consolidatesandbox"
            digest = hashlib.sha256((project / "src.txt").read_bytes()).hexdigest()
            identity = identitylib.parse_identity(
                f"project/{slug}/context/session", modules=frozenset(), project_slug=slug)
            value = assertionslib.normalize_value({"type": "string", "value": "runtime note"})
            hashed = assertionslib.assertion_hash(identity, identity.scope, value)
            stamp = statelib.now()
            record = {"schema_version": 1,
                      "candidate_id": statelib.new_identifier("cand"),
                      "kind": "unclassified", "state": stateslib.PENDING,
                      "created_at": stamp, "updated_at": stamp,
                      "source": {"origin": "test"},
                      "scope": {"project": slug},
                      "claim": "runtime note",
                      "identity": {"identity_key": identity.key,
                                   "identity_key_grammar_version":
                                       identitylib.IDENTITY_GRAMMAR_VERSION},
                      "assertion_hash": hashed["assertion_hash"],
                      "assertion_normalization_version":
                          assertionslib.NORMALIZATION_VERSION,
                      "hash_algorithm": assertionslib.HASH_ALGORITHM,
                      "assertion_value": hashed["value"],
                      "provenance": {"actor": "t", "origin": "test",
                                     "identity_confirmed_by": "t"},
                      "dependencies": [{"kind": "source_path", "ref": "src.txt",
                                        "digest": digest}]}
            storelib.append_candidate(project, record)
            (project / "src.txt").write_text("v2 changed\n", encoding="utf-8")
            report = consolidationlib.consolidate(project)
            proposal = report["proposals"][0]
            self.assertEqual("POTENTIALLY_STALE", proposal["staleness"])
            self.assertEqual(0.5, proposal["retrieval_penalty"])
            self.assertEqual(2, proposal["review_priority"])
            self.assertEqual(consolidationlib.NEEDS_EVIDENCE, proposal["outcome"])


if __name__ == "__main__":
    unittest.main()
