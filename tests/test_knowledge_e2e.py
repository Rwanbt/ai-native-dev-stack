"""K1-K4 behavioural E2E: the system as a whole, not modules in isolation.

Scenarios A-J from the convergence program: capture/persistence, dedup,
conflict, continuity, divergence, quarantine, degraded retrieval, isolation,
staleness and advisory consolidation - each with its safety invariant pinned.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import assertions as assertionslib
from ainative.knowledge import consolidation as consolidationlib
from ainative.knowledge import continuity as continuitylib
from ainative.knowledge import identity as identitylib
from ainative.knowledge import imports as importslib
from ainative.knowledge import planner as plannerlib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import states as stateslib
from ainative.knowledge import store as storelib
from ainative.lifecycle import state as statelib

REPO_ROOT = str(Path(__file__).resolve().parents[1])
RESTART_CODE = (
    "import sys, json; sys.path.insert(0, sys.argv[1]); "
    "from pathlib import Path; from ainative.knowledge import store; "
    "print(json.dumps([item.get('candidate_id') for item in "
    "store.list_candidates(Path(sys.argv[2]))]))")


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "notes.md").write_text("canonical text\n", encoding="utf-8")
    (project / "src.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _apply(project: Path, root: Path, slug: str, item: dict):
    source = root / "items.json"
    source.write_text(json.dumps([item]), encoding="utf-8")
    return importslib.apply(project, source, harness="claude", project_slug=slug)


def _canonical_snapshot(project: Path) -> dict:
    return {path.relative_to(project).as_posix(): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file() and ".ai-native" not in path.parts and ".git" not in path.parts}


class KnowledgeE2ETests(unittest.TestCase):
    def test_e2e_a_capture_persists_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "e2esandbox"
            applied = _apply(project, root, slug,
                             {"claim": "workflow review happens on Fridays",
                              "identity_key": f"project/{slug}/workflow/review"})
            created = applied["created"][0]
            restarted = subprocess.run(
                [sys.executable, "-c", RESTART_CODE, REPO_ROOT, str(project)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(0, restarted.returncode, restarted.stderr)
            self.assertIn(created, json.loads(restarted.stdout))

    def test_e2e_b_repeated_observation_proposes_merge_not_a_second_fact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "e2esandbox"
            item = {"claim": "workflow review happens on Fridays",
                    "identity_key": f"project/{slug}/workflow/review"}
            _apply(project, root, slug, item)
            _apply(project, root, slug, item)
            canonical = _canonical_snapshot(project)
            queue = reviewlib.review_queue(project)
            self.assertTrue(all(entry["outcome"] == "MERGE" for entry in queue["queue"]))
            self.assertEqual(canonical, _canonical_snapshot(project))

    def test_e2e_c_conflicting_observation_never_auto_resolves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "e2esandbox"
            key = f"project/{slug}/workflow/review"
            _apply(project, root, slug, {"claim": "review happens on Fridays", "identity_key": key})
            _apply(project, root, slug, {"claim": "review happens on Mondays", "identity_key": key})
            conflicts = reviewlib.conflicts(project)
            self.assertEqual(2, conflicts["count"])
            self.assertTrue(all(entry["outcome"] == "NEEDS_HUMAN"
                                for entry in conflicts["conflicts"]))
            self.assertTrue(all(item["state"] == stateslib.PENDING
                                for item in storelib.list_candidates(project)))

    def test_e2e_d_checkpoint_restores_after_compaction(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(
                project, {"task": "finish the E2E suite", "next_action": "run tests"},
                ttl_seconds=3600)
            restored = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(continuitylib.RESTORED, restored["status"])
            self.assertEqual("finish the E2E suite", restored["state"]["task"])

    def test_e2e_e_moved_head_surfaces_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, {"task": "t"}, ttl_seconds=3600)
            (project / "src.txt").write_text("v2\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(project), "commit", "-qm", "move"], check=True, capture_output=True)
            restored = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(continuitylib.STALE_HEAD, restored["status"])

    def test_e2e_e_changed_tree_surfaces_divergence_without_silent_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, {"task": "t"}, ttl_seconds=3600)
            (project / "notes.md").write_text("changed outside the checkpoint\n", encoding="utf-8")
            restored = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(continuitylib.DIVERGENCE, restored["status"])

    def test_e2e_f_secret_observation_is_quarantined_with_zero_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "e2esandbox"
            applied = _apply(project, root, slug,
                             {"claim": "api_key rotation happens every quarter",
                              "identity_key": f"project/{slug}/workflow/release"})
            self.assertEqual([], applied["created"])
            self.assertTrue(any("KNOWLEDGE_SECRET_REFUSED" in item["reason"]
                                for item in applied["refused"]))
            self.assertEqual([], storelib.list_candidates(project))

    def test_e2e_g_absent_recall_providers_keep_deterministic_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "e2esandbox"
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/review"})
            record = storelib.list_candidates(project)[0]
            source = plannerlib.candidate_source(record)
            bundle = plannerlib.plan([source], focus=[f"project/{slug}"])
            rendered = json.dumps(bundle.to_record(), sort_keys=True)
            self.assertIn("no recall providers in core", rendered)
            self.assertGreaterEqual(len(bundle.items), 1)

    def test_e2e_h_wrong_project_identity_is_refused_with_zero_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            other = root / "other-project"
            other.mkdir()
            applied = _apply(project, root, "e2esandbox",
                             {"claim": "rule", "identity_key": "project/other-project/context/session"})
            self.assertEqual([], applied["created"])
            self.assertTrue(any("KNOWLEDGE_IDENTITY_KEY_INVALID" in item["reason"]
                                for item in applied["refused"]))
            self.assertEqual([], storelib.list_candidates(project))
            self.assertFalse((other / ".ai-native").exists())

    def test_e2e_i_changed_dependency_marks_stale_without_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            slug = "e2esandbox"
            digest = hashlib.sha256((project / "src.txt").read_bytes()).hexdigest()
            identity = identitylib.parse_identity(
                f"project/{slug}/context/session", modules=frozenset(), project_slug=slug)
            value = assertionslib.normalize_value({"type": "string", "value": "runtime note"})
            hashed = assertionslib.assertion_hash(identity, identity.scope, value)
            stamp = statelib.now()
            record = {"schema_version": 1, "candidate_id": statelib.new_identifier("cand"),
                      "kind": "unclassified", "state": stateslib.PENDING,
                      "created_at": stamp, "updated_at": stamp,
                      "source": {"origin": "test"}, "scope": {"project": slug},
                      "claim": "runtime note",
                      "identity": {"identity_key": identity.key,
                                   "identity_key_grammar_version":
                                       identitylib.IDENTITY_GRAMMAR_VERSION},
                      "assertion_hash": hashed["assertion_hash"],
                      "assertion_normalization_version": assertionslib.NORMALIZATION_VERSION,
                      "hash_algorithm": assertionslib.HASH_ALGORITHM,
                      "assertion_value": hashed["value"],
                      "provenance": {"actor": "t", "origin": "test",
                                     "identity_confirmed_by": "t"},
                      "dependencies": [{"kind": "source_path", "ref": "src.txt",
                                        "digest": digest}]}
            storelib.append_candidate(project, record)
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            before_bytes = candidates.read_bytes()
            canonical = _canonical_snapshot(project)
            (project / "src.txt").write_text("drifted\n", encoding="utf-8")
            report = consolidationlib.consolidate(project)
            proposal = next(item for item in report["proposals"]
                            if item["candidate_id"] == record["candidate_id"])
            self.assertEqual("POTENTIALLY_STALE", proposal["staleness"])
            self.assertEqual(before_bytes, candidates.read_bytes())
            canonical["src.txt"] = (project / "src.txt").read_bytes()
            self.assertEqual(canonical, _canonical_snapshot(project))

    def test_e2e_j_consolidation_is_advisory_with_zero_canonical_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "e2esandbox"
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/review"})
            canonical = _canonical_snapshot(project)
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            before_bytes = candidates.read_bytes()
            report = consolidationlib.consolidate(project)
            self.assertTrue(report["proposals"])
            self.assertIn("advisory", report["note"])
            self.assertEqual(canonical, _canonical_snapshot(project))
            self.assertEqual(before_bytes, candidates.read_bytes())


if __name__ == "__main__":
    unittest.main()
