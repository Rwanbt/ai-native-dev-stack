"""Thin knowledge hooks: exit 0 everywhere, bounded effects, no policy."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS = REPO_ROOT / "hooks"


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".ai-native").mkdir()
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _run_hook(name: str, project: Path) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT)
    environment.pop("AINATIVE_BIN", None)
    environment.pop("AINATIVE_PROJECT", None)
    return subprocess.run(
        [sys.executable, str(HOOKS / name / "run.py")],
        input=json.dumps({"cwd": str(project)}), capture_output=True, text=True,
        env=environment, timeout=120, cwd=str(project))


def _working(project: Path) -> list:
    directory = project / ".ai-native" / "state" / "knowledge" / "working"
    return sorted(directory.glob("ckpt_*.json")) if directory.is_dir() else []


class KnowledgeHookTests(unittest.TestCase):
    def test_precompact_creates_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _run_hook("precompact-checkpoint", project)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(1, len(_working(project)))

    def test_session_start_restores_and_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            _run_hook("precompact-checkpoint", project)
            completed = _run_hook("session-start-context", project)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("RESTORED", completed.stdout)
            self.assertIn("working:", completed.stdout)

    def test_postedit_reads_staleness_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _run_hook("postedit-staleness", project)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("no candidates with dependency metadata", completed.stdout)
            self.assertEqual([], list((project / ".ai-native").rglob("candidates.jsonl")))

    def test_session_end_checkpoints_and_consolidates_advisory(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            completed = _run_hook("session-end-knowledge", project)
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(1, len(_working(project)))
            self.assertIn("advisory", completed.stdout)

    def test_hooks_are_safe_without_any_project_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            for name in ("session-start-context", "precompact-checkpoint",
                         "session-end-knowledge", "postedit-staleness"):
                completed = _run_hook(name, project)
                self.assertEqual(0, completed.returncode, f"{name}: {completed.stderr}")


if __name__ == "__main__":
    unittest.main()