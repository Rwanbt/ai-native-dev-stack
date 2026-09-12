"""Knowledge doctor section: measured status, honest degradation, fail-closed."""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.cli import main as cli_main
from ainative.knowledge import doctor as knowledgedoctor
from ainative.knowledge import imports as importslib


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _apply(project: Path, root: Path, slug: str, item: dict):
    source = root / "items.json"
    source.write_text(json.dumps([item]), encoding="utf-8")
    return importslib.apply(project, source, harness="claude", project_slug=slug)


class KnowledgeDoctorTests(unittest.TestCase):
    def test_absent_store_reports_honest_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            report = knowledgedoctor.knowledge_status(project)
            self.assertEqual("ABSENT", report["status"])
            self.assertEqual("GATE_CLOSED", report["promotion_mode"])
            self.assertEqual("UNVERIFIED", report["trust"])
            self.assertEqual("ABSENT", report["semantic_provider"])

    def test_ok_store_reports_counts_and_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "doctorsandbox"
            key = f"project/{slug}/workflow/review"
            _apply(project, root, slug, {"claim": "review happens on Fridays", "identity_key": key})
            _apply(project, root, slug, {"claim": "review happens on Mondays", "identity_key": key})
            report = knowledgedoctor.knowledge_status(project)
            self.assertEqual("OK", report["status"])
            self.assertEqual(2, report["candidates"])
            self.assertEqual(2, report["review_backlog"])
            self.assertEqual(2, report["conflicts"])
            self.assertEqual(0, report["stale"])

    def test_corrupt_store_reports_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "doctorsandbox"
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/review"})
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            candidates.write_text("not an envelope\n", encoding="utf-8")
            report = knowledgedoctor.knowledge_status(project)
            self.assertEqual("FAIL", report["status"])

    def test_doctor_json_includes_the_knowledge_section(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                cli_main(["doctor", "--project", str(project), "--json"])
            record = json.loads(output.getvalue())
            self.assertIn("knowledge", record)
            self.assertEqual("ABSENT", record["knowledge"]["status"])
            self.assertEqual("GATE_CLOSED", record["knowledge"]["promotion_mode"])


if __name__ == "__main__":
    unittest.main()
