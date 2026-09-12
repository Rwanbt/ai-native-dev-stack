"""Context CLI: checkpoint/save/restore/status/clear on the continuity owner."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.cli import main as cli_main
from ainative.knowledge import continuity as continuitylib


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "work.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _run(*arguments) -> tuple[int, str]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = cli_main(list(arguments))
    return code, output.getvalue()


class ContextCliTests(unittest.TestCase):
    def test_checkpoint_and_restore_latest_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            state = {"task": "finish hooks", "next_action": "write adapters",
                     "hypotheses": ["thin wrappers suffice"]}
            code, output = _run("context", "checkpoint", "--project", str(project),
                                "--state-json", json.dumps(state), "--ttl", "3600")
            self.assertEqual(0, code)
            self.assertIn("saved", output)
            code, output = _run("context", "restore", "--project", str(project))
            self.assertEqual(0, code)
            self.assertIn("RESTORED", output)

    def test_save_alias_works(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            code, output = _run("context", "save", "--project", str(project),
                                "--state-json", json.dumps({"task": "t"}))
            self.assertEqual(0, code)
            self.assertIn("saved", output)

    def test_status_reports_footprint(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            _run("context", "checkpoint", "--project", str(project),
                 "--state-json", json.dumps({"task": "t"}), "--ttl", "3600")
            code, output = _run("context", "status", "--project", str(project))
            self.assertEqual(0, code)
            self.assertIn("1 checkpoint(s)", output)

    def test_clear_dry_run_removes_nothing_and_apply_prunes_expired(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            _run("context", "checkpoint", "--project", str(project),
                 "--state-json", json.dumps({"task": "expired"}), "--ttl", "-1")
            _run("context", "checkpoint", "--project", str(project),
                 "--state-json", json.dumps({"task": "valid"}), "--ttl", "3600")
            code, output = _run("context", "clear", "--project", str(project))
            self.assertEqual(0, code)
            self.assertIn("dry-run", output)
            self.assertEqual(2, continuitylib.checkpoint_status(project)["checkpoints"])
            code, output = _run("context", "clear", "--project", str(project), "--apply")
            self.assertEqual(0, code)
            status = continuitylib.checkpoint_status(project)
            self.assertEqual(1, status["checkpoints"])
            self.assertEqual(0, status["expired"])

    def test_restore_without_any_checkpoint_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            code, output = _run("context", "restore", "--project", str(project))
            self.assertEqual(0, code)
            self.assertIn("MISSING", output)

    def test_moved_head_is_surfaced_not_silently_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            _run("context", "checkpoint", "--project", str(project),
                 "--state-json", json.dumps({"task": "t"}), "--ttl", "3600")
            (project / "work.txt").write_text("v2\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(project), "commit", "-qm", "move"], check=True, capture_output=True)
            code, output = _run("context", "restore", "--project", str(project))
            self.assertIn("STALE_HEAD", output)


if __name__ == "__main__":
    unittest.main()
