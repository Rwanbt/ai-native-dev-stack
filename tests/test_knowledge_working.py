"""K2 gates: crash recovery, checkpoints, stale heads, bounds, TTL."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import working as workinglib
from ainative.knowledge.errors import KnowledgeError


def _state(**overrides):
    record = {"task": "Implement K2", "next_action": "write tests",
              "files_touched": ["ainative/knowledge/working.py"]}
    record.update(overrides)
    return workinglib.WorkingState.from_record(
        {**workinglib.WorkingState().to_record(), **record})


class SaveLoadTest(unittest.TestCase):
    def test_Save_Load_RoundTrips(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state())
            state, outcome = workinglib.load(project)
            self.assertEqual(outcome, workinglib.CURRENT)
            self.assertEqual(state.task, "Implement K2")
            self.assertEqual(state.next_action, "write tests")

    def test_Load_MissingFiles_ReturnsEmpty(self):
        with tempfile.TemporaryDirectory() as directory:
            state, outcome = workinglib.load(Path(directory))
            self.assertEqual((state, outcome), (None, workinglib.EMPTY))

    def test_Concurrency_SequentialSaves_LastWinsWithoutCorruption(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state(task="first"))
            workinglib.save(project, _state(task="second"))
            state, outcome = workinglib.load(project)
            self.assertEqual((state.task, outcome), ("second", workinglib.CURRENT))


class CrashRecoveryTest(unittest.TestCase):
    def _with_backup(self, project: Path) -> None:
        workinglib.save(project, _state(task="v1"))
        workinglib.save(project, _state(task="v2"))

    def test_Crash_CorruptCurrent_RecoversFromBackup(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._with_backup(project)
            workinglib.working_path(project).write_text("not json{{", encoding="utf-8")
            state, outcome = workinglib.load(project)
            self.assertEqual(outcome, workinglib.RECOVERED)
            self.assertEqual(state.task, "v1")

    def test_Crash_TruncatedWrite_RecoversFromBackup(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._with_backup(project)
            raw = workinglib.working_path(project).read_bytes()
            workinglib.working_path(project).write_bytes(raw[: len(raw) // 2])
            state, outcome = workinglib.load(project)
            self.assertEqual((outcome, state.task),
                             (workinglib.RECOVERED, "v1"))

    def test_Crash_BothCorrupt_FailsCleanlyWithoutFabrication(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self._with_backup(project)
            workinglib.working_path(project).write_text("garbage", encoding="utf-8")
            workinglib.backup_path(project).write_text("garbage", encoding="utf-8")
            with self.assertRaises(KnowledgeError) as caught:
                workinglib.load(project)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_STORE_CORRUPTED")


class CheckpointTest(unittest.TestCase):
    def test_Checkpoint_Restore_RoundTrips(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state())
            record = workinglib.checkpoint(project, reason="precompact")
            self.assertEqual(record["reason"], "precompact")
            workinglib.save(project, _state(task="moved on"))
            restored, outcome = workinglib.restore(project, record["checkpoint_id"])
            self.assertEqual(outcome, workinglib.RESTORED)
            self.assertEqual(restored["working"]["task"], "Implement K2")
            state, _ = workinglib.load(project)
            self.assertEqual(state.task, "Implement K2")

    def test_Restore_ForgedHead_RequiresReconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state())
            record = workinglib.checkpoint(project)
            path = (workinglib.checkpoints_dir(project)
                    / f"{record['checkpoint_id']}.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["repository_head"] = "deadbeef" * 5
            path.write_text(json.dumps(payload), encoding="utf-8")
            _, outcome = workinglib.restore(project, record["checkpoint_id"])
            self.assertEqual(outcome, workinglib.RESTORE_REQUIRES_RECONCILIATION)

    def test_Restore_UnknownId_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KnowledgeError) as caught:
                workinglib.restore(Path(directory), "ckpt_" + "0" * 32)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_NOT_FOUND")

    def test_Restore_TraversalId_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KnowledgeError) as caught:
                workinglib.restore(Path(directory), "../escape")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_Checkpoint_EmptyState_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KnowledgeError) as caught:
                workinglib.checkpoint(Path(directory))
            self.assertEqual(caught.exception.code, "KNOWLEDGE_NOT_FOUND")

    def test_Checkpoint_OversizeReason_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state())
            with self.assertRaises(KnowledgeError) as caught:
                workinglib.checkpoint(project, reason="x" * 201)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_Checkpoint_PruneEnforcesBound(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state())
            for _ in range(workinglib.MAX_CHECKPOINTS + 1):
                workinglib.checkpoint(project)
            self.assertEqual(len(workinglib.list_checkpoints(project)),
                             workinglib.MAX_CHECKPOINTS)


class BoundsTest(unittest.TestCase):
    def test_Bounds_TooManyItems_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            _state(files_touched=[f"f{i}.py" for i in range(201)])
        self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_Bounds_OversizeText_Refused(self):
        with self.assertRaises(KnowledgeError) as caught:
            _state(task="x" * 4001)
        self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_TTL_Expiry_Reported(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state(expires_at="2000-01-01T00:00:00+00:00"))
            _, outcome = workinglib.load(project)
            self.assertEqual(outcome, workinglib.EXPIRED)

    def test_Clear_RemovesAll(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workinglib.save(project, _state())
            workinglib.checkpoint(project)
            removed = workinglib.clear(project)
            self.assertTrue(removed)
            self.assertEqual(workinglib.load(project), (None, workinglib.EMPTY))


if __name__ == "__main__":
    unittest.main()