"""Cross-harness import: identity via the owner, preview-first, no canonical writes."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import imports as importslib
from ainative.knowledge.errors import KnowledgeError


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "notes.md").write_text("canonical text\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _write(source_dir: Path, name: str, payload) -> Path:
    path = source_dir / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ImportPreviewTests(unittest.TestCase):
    def test_preview_resolves_and_refuses_with_zero_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "importsandbox"
            source = _write(root, "memories.json", [
                {"claim": "workflow review happens on Fridays",
                 "identity_key": f"project/{slug}/workflow/review"},
                {"claim": "no identity at all"},
            ])
            report = importslib.preview(source, harness="claude", project_slug=slug)
            self.assertEqual(2, report["parsed"])
            self.assertEqual(1, len(report["staged"]))
            self.assertEqual(1, len(report["refused"]))
            self.assertIn("KNOWLEDGE_IDENTITY_KEY_INVALID", report["refused"][0]["reason"])
            self.assertFalse((project / ".ai-native").exists())

    def test_wrong_project_identity_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "importsandbox"
            source = _write(root, "memories.json", [
                {"claim": "rule", "identity_key": "project/somewhere-else/context/session"},
            ])
            report = importslib.preview(source, harness="claude", project_slug=slug)
            self.assertEqual(0, len(report["staged"]))
            self.assertTrue(report["refused"])

    def test_unknown_module_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "importsandbox"
            source = _write(root, "memories.json", [
                {"claim": "rule", "identity_key": "module/ghost/context/session"},
            ])
            report = importslib.preview(source, harness="claude", project_slug=slug)
            self.assertEqual(0, len(report["staged"]))
            self.assertTrue(report["refused"])

    def test_markdown_bullets_parse_and_require_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "importsandbox"
            source = _write(root, "memories.md", "- first bullet\n* second bullet\n")
            report = importslib.preview(source, harness="codex", project_slug=slug)
            self.assertEqual(2, report["parsed"])
            self.assertEqual(0, len(report["staged"]))
            self.assertEqual(2, len(report["refused"]))


class ImportApplyTests(unittest.TestCase):
    def test_apply_stages_pending_candidate_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "importsandbox"
            source = _write(root, "memories.json", [
                {"claim": "workflow review happens on Fridays",
                 "identity_key": f"project/{slug}/workflow/review",
                 "kind": "workflow-rule", "session": "sess-42"},
            ])
            report = importslib.apply(project, source, harness="claude",
                                      project_slug=slug, actor="operator-t",
                                      origin_project="other-project",
                                      origin_repository="other-repo",
                                      origin_session="sess-42")
            self.assertEqual(1, len(report["created"]))
            self.assertEqual(0, len(report["refused"]))
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            self.assertTrue(candidates.is_file())
            line = candidates.read_text(encoding="utf-8").splitlines()[0]
            self.assertIn("import_claude", line)
            self.assertIn("other-project", line)
            self.assertIn("sess-42", line)

    def test_apply_never_touches_canonical_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "importsandbox"
            before = (project / "notes.md").read_text(encoding="utf-8")
            source = _write(root, "memories.json", [
                {"claim": "workflow review happens on Fridays",
                 "identity_key": f"project/{slug}/workflow/review"},
            ])
            importslib.apply(project, source, harness="claude", project_slug=slug)
            self.assertEqual(before, (project / "notes.md").read_text(encoding="utf-8"))

    def test_unknown_harness_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            source = _write(root, "memories.json", [])
            with self.assertRaises(KnowledgeError):
                importslib.preview(source, harness="alien", project_slug="x")


if __name__ == "__main__":
    unittest.main()
