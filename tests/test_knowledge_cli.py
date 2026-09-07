"""PR5 gates: knowledge CLI contract (status/learn/candidates/inspect/reject)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


def _repo(directory: str) -> Path:
    if GIT is None:
        raise unittest.SkipTest("git executable required")
    project = Path(directory)
    subprocess.run([GIT, "-C", str(project), "init", "-q"], check=True,
                   capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    return project


def _cli(project: Path, *args: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8",
                   "PYTHONPATH": str(REPO)}
    return subprocess.run([sys.executable, "-m", "ainative.cli", "knowledge",
                           *args, "--project", str(project)],
                          capture_output=True, text=True, env=environment,
                          stdin=subprocess.DEVNULL, cwd=str(REPO))


def _learn(project: Path, **overrides) -> str:
    arguments = ["learn", "--claim", "Retries need explicit budgets.",
                 "--kind", "rule", "--identity-key",
                 "project/demo/rule/retry", "--project-slug", "demo"]
    for key, value in overrides.items():
        arguments += [f"--{key.replace('_', '-')}", value]
    completed = _cli(project, *arguments, "--json")
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)["candidate"]["candidate_id"]


class KnowledgeCliTest(unittest.TestCase):
    def test_Status_Empty_Json(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _cli(project, "status", "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["storage"]["counts"]["candidates"], 0)

    def test_Learn_Inspect_RoundTrip(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            identifier = _learn(project)
            inspected = _cli(project, "inspect", identifier, "--json")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            payload = json.loads(inspected.stdout)
            self.assertEqual(payload["candidate"]["state"], "PENDING")
            self.assertEqual(payload["candidate"]["kind"], "rule")

    def test_Learn_DryRun_WritesNothing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _cli(project, "learn", "--claim", "x", "--kind", "rule",
                             "--identity-key", "project/demo/rule/limit",
                             "--project-slug", "demo",
                             "--dry-run", "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            listed = _cli(project, "candidates", "--json")
            self.assertEqual(json.loads(listed.stdout)["total"], 0)

    def test_Learn_SecretClaim_RefusedClean(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _cli(project, "learn", "--claim",
                             "deploy with api_key = abc", "--kind", "rule",
                             "--identity-key", "project/demo/rule/limit",
                             "--project-slug", "demo")
            self.assertEqual(completed.returncode, 2, completed.stdout)
            self.assertIn("KNOWLEDGE_SECRET_REFUSED", completed.stderr)
            self.assertNotIn("abc", completed.stderr)
            self.assertNotIn("abc", completed.stdout)

    def test_Reject_LegalAndIllegal(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            identifier = _learn(project)
            refused = _cli(project, "reject", identifier, "--dry-run")
            self.assertEqual(refused.returncode, 0, refused.stderr)
            done = _cli(project, "reject", identifier, "--actor", "lead",
                        "--reason", "duplicate", "--json")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout)["candidate"]["state"],
                             "REJECTED")
            again = _cli(project, "reject", identifier)
            self.assertEqual(again.returncode, 2, again.stdout)
            self.assertIn("KNOWLEDGE_ILLEGAL_STATE_TRANSITION", again.stderr)

    def test_Candidates_FilterAndLimit(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            first = _learn(project)
            _learn(project)
            self.knowledge_reject(project, first)
            filtered = _cli(project, "candidates", "--status", "REJECTED",
                            "--json")
            payload = json.loads(filtered.stdout)
            self.assertEqual(payload["total"], 1)
            limited = _cli(project, "candidates", "--limit", "1", "--json")
            self.assertEqual(len(json.loads(limited.stdout)["candidates"]), 1)
            bad = _cli(project, "candidates", "--status", "NOPE")
            self.assertEqual(bad.returncode, 2, bad.stdout)

    def knowledge_reject(self, project: Path, identifier: str) -> None:
        completed = _cli(project, "reject", identifier)
        assert completed.returncode == 0, completed.stderr

    def test_Inspect_Unknown_ExitOne(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _cli(project, "inspect", "missing-id")
            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertIn("KNOWLEDGE_NOT_FOUND", completed.stderr)

    def test_EveryCommand_JsonParses(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            identifier = _learn(project)
            for command in (("status", "--json"),
                            ("candidates", "--json"),
                            ("inspect", identifier, "--json")):
                with self.subTest(command=command[0]):
                    completed = _cli(project, *command)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    json.loads(completed.stdout)

if __name__ == "__main__":
    unittest.main()
