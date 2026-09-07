"""K8 gates: preview-first staging, quarantine, per-item refusal."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import imports as importslib
from ainative.knowledge import store as storelib
from ainative.knowledge.errors import KnowledgeError
from tests.lifecycle_support import LifecycleTestCase


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


class ParseTest(unittest.TestCase):
    def test_Markdown_BulletsParsed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory), "notes.md",
                          "# Learnings\n\n- Never mock the database.\n- Flaky sunset job.\n")
            items = importslib.parse(path)
            self.assertEqual([item["claim"] for item in items],
                             ["Never mock the database.", "Flaky sunset job."])

    def test_Json_ItemsValidated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory), "out.json", json.dumps(
                [{"claim": "Use real DB.", "kind": "PROJECT_RULE",
                  "evidence": [{"type": "TEST", "locator": "t.py"}]}]))
            items = importslib.parse(path)
            self.assertEqual(items[0]["kind"], "PROJECT_RULE")

    def test_Json_MissingClaim_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory), "out.json", json.dumps([{"kind": "X"}]))
            with self.assertRaises(KnowledgeError) as caught:
                importslib.parse(path)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_UnknownHarness_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory), "n.md", "- Something.\n")
            with self.assertRaises(KnowledgeError) as caught:
                importslib.preview(path, harness="clippy")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_OversizeImport_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = _write(Path(directory), "big.md", "- x\n" * 101)
            with self.assertRaises(KnowledgeError) as caught:
                importslib.parse(path)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")


class ApplyTest(unittest.TestCase):
    def test_Preview_WritesNothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _write(root, "n.md", "- Never mock the database.\n")
            report = importslib.preview(source, harness="claude")
            self.assertEqual(report["parsed"], 1)
            self.assertFalse((root / ".ai-native").exists())

    def test_Apply_StagesPendingWithImportProvenance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = _write(project, "n.md", "- Never mock the database.\n")
            outcome = importslib.apply(project, source, harness="codex",
                                       actor="tester")
            self.assertEqual(len(outcome["created"]), 1)
            stored = storelib.inspect_candidate(project, outcome["created"][0])
            self.assertEqual(stored["status"], "PENDING")
            self.assertEqual(stored["scope"]["agent"], "codex")
            self.assertEqual(stored["provenance"]["origin_type"], "import_codex")

    def test_Apply_SecretItem_SkippedAndReported(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = _write(project, "n.md",
                            "- Good rule.\n- Deploy with api_key = abc123XYZ.\n")
            outcome = importslib.apply(project, source, harness="opencode",
                                       actor="tester")
            self.assertEqual(len(outcome["created"]), 1)
            self.assertEqual(len(outcome["refused"]), 1)
            self.assertIn("SECRET", outcome["refused"][0]["reason"])
            claims = [item["claim"] for item in storelib.read_all(project)]
            self.assertTrue(all("api_key" not in claim for claim in claims))


class ImportCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def test_Import_PreviewThenApply_Json(self):
        source = self.project / "learnings.md"
        source.write_text("- Retries need explicit budgets.\n", encoding="utf-8")
        preview = self.knowledge("import", "--harness", "claude",
                                 "--file", str(source), "--json")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(json.loads(preview.stdout)["apply"])
        self.assertFalse((self.project / ".ai-native" / "knowledge").exists())
        applied = self.knowledge("import", "--harness", "claude",
                                 "--file", str(source), "--apply", "--json")
        payload = json.loads(applied.stdout)
        self.assertEqual(len(payload["created"]), 1)
        inspected = self.knowledge("inspect", payload["created"][0], "--json")
        self.assertEqual(json.loads(inspected.stdout)["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()