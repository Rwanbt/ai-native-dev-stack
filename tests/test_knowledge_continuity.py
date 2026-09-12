"""PR10 gates: checkpoints bound to repo state, explicit divergence."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ainative.knowledge import continuity as continuitylib
from ainative.knowledge.errors import KnowledgeError

GIT = shutil.which("git")


def _repo(directory: str) -> Path:
    if GIT is None:
        raise unittest.SkipTest("git executable required")
    project = Path(directory)
    subprocess.run([GIT, "-C", str(project), "init", "-q"], check=True,
                   capture_output=True)
    subprocess.run([GIT, "-C", str(project), "config", "user.email", "t@t"],
                   check=True, capture_output=True)
    subprocess.run([GIT, "-C", str(project), "config", "user.name", "t"],
                   check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "work.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run([GIT, "-C", str(project), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run([GIT, "-C", str(project), "commit", "-qm", "seed"],
                   check=True, capture_output=True)
    return project


def _state(**overrides) -> dict:
    record = {"task": "Migrate module X", "files_touched": ["src/a.py"],
              "open_work": ["write tests"], "blockers": [], "tests_run": []}
    record.update(overrides)
    return record


def _checkpoint_worker(args: tuple) -> str:
    project_str, worker = args
    from ainative.knowledge import continuity as continuity_module
    record = continuity_module.checkpoint(
        Path(project_str), _state(task=f"task {worker}"))
    return record["checkpoint_id"]


class ContinuityTest(unittest.TestCase):
    def test_Checkpoint_Restore_RoundTrip(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, _state())
            outcome = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(outcome["status"], "RESTORED")
            self.assertEqual(outcome["state"]["task"], "Migrate module X")

    def test_DirtyTree_SameHead_Diverges(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, _state())
            (project / "work.txt").write_text("v2-dirty\n", encoding="utf-8")
            outcome = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(outcome["status"], "RESTORE_DIRTY_TREE_DIVERGENCE")
            self.assertEqual(outcome["state"]["task"], "Migrate module X")

    def test_HeadMoved_Stale(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, _state())
            (project / "work.txt").write_text("v2\n", encoding="utf-8")
            subprocess.run([GIT, "-C", str(project), "add", "-A"], check=True,
                           capture_output=True)
            subprocess.run([GIT, "-C", str(project), "commit", "-qm", "v2"],
                           check=True, capture_output=True)
            outcome = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(outcome["status"], "STALE_HEAD")

    def test_TtlExpiry_Reported(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, _state(), ttl_seconds=-1)
            outcome = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(outcome["status"], "EXPIRED")

    def test_UnknownId_Missing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            outcome = continuitylib.restore(project, "ckpt_missing")
            self.assertEqual(outcome["status"], "MISSING")

    def test_CorruptFile_FailsClosed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = continuitylib.checkpoint(project, _state())
            path = (project / ".ai-native" / "state" / "knowledge"
                    / "working" / f"{record['checkpoint_id']}.json")
            path.write_bytes(b"{torn")
            with self.assertRaises(KnowledgeError) as caught:
                continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(caught.exception.code, "KNOWLEDGE_STORE_CORRUPTED")

    def test_ChainOfThoughtField_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with self.assertRaises(KnowledgeError):
                continuitylib.checkpoint(
                    project, _state(chain_of_thought="secret reasoning"))

    def test_SecretTask_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with self.assertRaises(KnowledgeError) as caught:
                continuitylib.checkpoint(
                    project, _state(task="deploy with api_key = abc"))
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_ConcurrentCheckpoints_AllDurable(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with ProcessPoolExecutor(max_workers=4) as pool:
                identifiers = list(pool.map(_checkpoint_worker,
                                            [(str(project), index)
                                             for index in range(8)]))
            self.assertEqual(len(set(identifiers)), 8)
            listed = continuitylib.list_checkpoints(project)
            self.assertGreaterEqual(len(listed), 8)

    def test_RetentionBound_Enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            for _ in range(continuitylib.MAX_CHECKPOINTS + 3):
                continuitylib.checkpoint(project, _state())
            self.assertLessEqual(len(continuitylib.list_checkpoints(project)),
                                 continuitylib.MAX_CHECKPOINTS)


if __name__ == "__main__":
    unittest.main()


class WorkingMemoryExtensionTests(unittest.TestCase):
    def test_extended_fields_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            state = _state(next_action="run the suite",
                           hypotheses=["store is bounded"],
                           findings=["flaky test isolated"],
                           questions=["when is the K5 gate?"],
                           candidate_ids=["cand_example"])
            record = continuitylib.checkpoint(project, state, ttl_seconds=3600)
            self.assertEqual("run the suite", record["state"]["next_action"])
            restored = continuitylib.restore(project, record["checkpoint_id"])
            self.assertEqual(continuitylib.RESTORED, restored["status"])
            self.assertEqual(state["hypotheses"], restored["state"]["hypotheses"])
            self.assertEqual(state["findings"], restored["state"]["findings"])
            self.assertEqual(state["questions"], restored["state"]["questions"])
            self.assertEqual(state["candidate_ids"], restored["state"]["candidate_ids"])

    def test_legacy_shaped_state_still_validates_with_defaults(self):
        validated = continuitylib.validate_state(_state())
        for name in ("next_action", "hypotheses", "findings", "questions",
                     "candidate_ids"):
            self.assertIn(name, validated)
        self.assertEqual("", validated["next_action"])
        self.assertEqual([], validated["candidate_ids"])

    def test_chain_of_thought_is_still_refused(self):
        with self.assertRaises(KnowledgeError):
            continuitylib.validate_state(_state(chain_of_thought=["hidden reasoning"]))

    def test_extended_fields_are_bounded(self):
        with self.assertRaises(KnowledgeError):
            continuitylib.validate_state(_state(questions=[f"q{i}" for i in range(101)]))
        with self.assertRaises(KnowledgeError):
            continuitylib.validate_state(_state(findings=["x" * 2001]))
        with self.assertRaises(KnowledgeError):
            continuitylib.validate_state(_state(next_action=["not", "text"]))
