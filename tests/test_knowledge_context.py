"""K2 CLI gates: `ainative context` save/checkpoint/restore/clear."""

from __future__ import annotations

import json
import subprocess
import unittest

from tests.lifecycle_support import LifecycleTestCase


class KnowledgeContextCliTest(LifecycleTestCase):
    def context(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("context", *args)

    def test_Status_Empty_ExitZero(self):
        completed = self.context("status")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("empty", completed.stdout)

    def test_Save_Checkpoint_Restore_RoundTrip(self):
        saved = self.context("save", "--task", "Implement K2",
                             "--next-action", "write tests")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        made = self.context("checkpoint", "--reason", "precompact", "--json")
        self.assertEqual(made.returncode, 0, made.stderr)
        checkpoint_id = json.loads(made.stdout)["checkpoint_id"]
        self.context("save", "--task", "moved on")
        restored = self.context("restore", checkpoint_id)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        status = self.context("status", "--json")
        payload = json.loads(status.stdout)
        self.assertEqual(payload["working"]["task"], "Implement K2")

    def test_Save_MergesAcrossCalls(self):
        self.context("save", "--task", "K2", "--touch", "a.py")
        self.context("save", "--touch", "b.py", "--blocker", "none")
        status = self.context("status", "--json")
        working = json.loads(status.stdout)["working"]
        self.assertEqual(working["task"], "K2")
        self.assertEqual(working["files_touched"], ["a.py", "b.py"])
        self.assertEqual(working["blockers"], ["none"])

    def test_Clear_RequiresYes(self):
        self.context("save", "--task", "K2")
        refused = self.context("clear")
        self.assertEqual(refused.returncode, 2, refused.stdout)
        self.assertIn("KNOWLEDGE_CONFIRMATION_REQUIRED", refused.stderr)
        cleared = self.context("clear", "--yes")
        self.assertEqual(cleared.returncode, 0, cleared.stderr)
        self.assertIn("empty", self.context("status").stdout)

    def test_EveryContextCommand_EmitsParseableJson(self):
        self.context("save", "--task", "K2")
        made = self.context("checkpoint", "--json")
        checkpoint_id = json.loads(made.stdout)["checkpoint_id"]
        for command in (("status", "--json"),
                        ("save", "--task", "K2", "--dry-run", "--json"),
                        ("checkpoint", "--dry-run", "--json"),
                        ("restore", checkpoint_id, "--dry-run", "--json"),
                        ("clear", "--dry-run", "--json")):
            with self.subTest(command=command[0]):
                completed = self.context(*command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                try:
                    json.loads(completed.stdout)
                except ValueError:
                    self.fail(f"{command} did not emit JSON:\n{completed.stdout[:400]}")


if __name__ == "__main__":
    unittest.main()