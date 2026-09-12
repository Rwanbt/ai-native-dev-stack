"""Staleness: mark never rewrite; decay ranking-only; corrupt metadata fails closed."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import imports as importslib
from ainative.knowledge import staleness as stalenesslib
from ainative.knowledge import store as storelib
from ainative.knowledge.errors import KnowledgeError


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "src.txt").write_text("content v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StalenessTests(unittest.TestCase):
    def test_unchanged_dependency_is_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            digest = _sha(project / "src.txt")
            result = stalenesslib.evaluate(
                project, [{"kind": "source_path", "ref": "src.txt", "digest": digest}])
            self.assertEqual(stalenesslib.FRESH, result["signal"])
            self.assertEqual(stalenesslib.FRESH, result["details"][0]["signal"])

    def test_changed_source_file_is_potentially_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            digest = _sha(project / "src.txt")
            (project / "src.txt").write_text("content v2\n", encoding="utf-8")
            result = stalenesslib.evaluate(
                project, [{"kind": "source_path", "ref": "src.txt", "digest": digest}])
            self.assertEqual(stalenesslib.POTENTIALLY_STALE, result["signal"])

    def test_deleted_source_is_stale_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            digest = _sha(project / "src.txt")
            os.remove(project / "src.txt")
            result = stalenesslib.evaluate(
                project, [{"kind": "source_path", "ref": "src.txt", "digest": digest}])
            self.assertEqual(stalenesslib.STALE_UNRESOLVED, result["signal"])

    def test_unknown_dependency_kind_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            result = stalenesslib.evaluate(
                project, [{"kind": "quantum_entanglement", "ref": "x"}])
            self.assertEqual(stalenesslib.UNKNOWN, result["signal"])

    def test_no_dependencies_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            self.assertEqual(stalenesslib.UNKNOWN,
                             stalenesslib.evaluate(project, [])["signal"])

    def test_hard_class_never_decays(self):
        self.assertEqual(stalenesslib.NO_DECAY,
                         stalenesslib.decay_class({"decay_class": "no_decay"}))
        self.assertEqual(stalenesslib.WEAK_DECAY, stalenesslib.decay_class({}))
        self.assertEqual(0.0, stalenesslib.retrieval_penalty(
            stalenesslib.STALE_UNRESOLVED, stalenesslib.NO_DECAY))
        self.assertEqual(1.0, stalenesslib.retrieval_penalty(
            stalenesslib.STALE_UNRESOLVED, stalenesslib.WEAK_DECAY))
        self.assertEqual(1.5, stalenesslib.retrieval_penalty(
            stalenesslib.STALE_UNRESOLVED, stalenesslib.STRONGER_DECAY))

    def test_review_priority_ranks_without_authority(self):
        self.assertEqual(0, stalenesslib.review_priority(stalenesslib.FRESH,
                                                         stalenesslib.WEAK_DECAY))
        self.assertEqual(2, stalenesslib.review_priority(stalenesslib.POTENTIALLY_STALE,
                                                         stalenesslib.WEAK_DECAY))
        self.assertEqual(3, stalenesslib.review_priority(stalenesslib.POTENTIALLY_STALE,
                                                         stalenesslib.STRONGER_DECAY))
        self.assertEqual(2, stalenesslib.review_priority(stalenesslib.POTENTIALLY_STALE,
                                                         stalenesslib.NO_DECAY))

    def test_stale_result_writes_nothing_and_transitions_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "stalesandbox"
            source = root / "export.json"
            source.write_text(json.dumps([{"claim": "workflow review happens on Fridays",
                                           "identity_key": f"project/{slug}/workflow/review"}]),
                              encoding="utf-8")
            importslib.apply(project, source, harness="claude", project_slug=slug)
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            before_bytes = candidates.read_bytes()
            before_states = [item.get("state") for item in storelib.list_candidates(project)]
            digest = _sha(project / "src.txt")
            (project / "src.txt").write_text("drifted\n", encoding="utf-8")
            result = stalenesslib.evaluate(
                project, [{"kind": "source_path", "ref": "src.txt", "digest": digest}])
            self.assertEqual(stalenesslib.POTENTIALLY_STALE, result["signal"])
            self.assertEqual(before_bytes, candidates.read_bytes())
            self.assertEqual(before_states,
                             [item.get("state") for item in storelib.list_candidates(project)])

    def test_cross_domain_dependency_is_refused_and_invisible(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            outside = Path(directory).parent / "elsewhere.txt"
            result = stalenesslib.evaluate(project, [
                {"kind": "source_path", "ref": "../elsewhere.txt", "digest": "x"},
                {"kind": "source_path", "ref": str(outside), "digest": "x"},
            ])
            self.assertEqual(2, len(result["refused"]))
            self.assertEqual(stalenesslib.DEPENDENCY_REFUSED, result["refused"][0]["code"])
            self.assertEqual(stalenesslib.UNKNOWN, result["signal"])

    def test_corrupt_dependency_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with self.assertRaises(KnowledgeError):
                stalenesslib.evaluate(project, "not a list")
            with self.assertRaises(KnowledgeError):
                stalenesslib.evaluate(project, [{"ref": "no-kind"}])
            with self.assertRaises(KnowledgeError):
                stalenesslib.evaluate(project, [{"kind": "source_path"}])


if __name__ == "__main__":
    unittest.main()
