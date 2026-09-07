"""K5a gates: deterministic bundles, nearest-context walk, hard budgets."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import retrieval as retrievallib
from ainative.knowledge import store as storelib
from ainative.knowledge.candidate import capture
from ainative.knowledge.errors import KnowledgeError
from tests.lifecycle_support import LifecycleTestCase


def _write(project: Path, relative: str, content: str) -> Path:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _seed(project: Path) -> None:
    _write(project, "AGENTS.md", "# Rules\n")
    _write(project, "AI_CONTEXT.md", "# Root context\n")
    _write(project, "AI_SUMMARY.md", "# Summary\n")
    _write(project, "vault/AI_CONTEXT.md", "# Vault context\n")
    _write(project, "docs/adr/0017-x.md", "# ADR-0017\n")


class DeterministicTest(unittest.TestCase):
    def test_Bundle_ContainsAgentsAndNearestContext(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seed(project)
            bundle = retrievallib.assemble(project, focus=["vault/notes.md"])
            locators = [item.locator for item in bundle.items]
            self.assertIn("AGENTS.md", locators)
            self.assertIn("vault/AI_CONTEXT.md", locators)
            self.assertNotIn("AI_CONTEXT.md", locators)

    def test_Bundle_RootFocus_UsesRootContext(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seed(project)
            bundle = retrievallib.assemble(project, focus=["."])
            kinds = {item.kind: item.locator for item in bundle.items}
            self.assertEqual(kinds.get("AI_CONTEXT.md"), "AI_CONTEXT.md")

    def test_Bundle_NamedAdr_Included(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seed(project)
            bundle = retrievallib.assemble(project, adr_refs=["0017"])
            self.assertTrue(any(item.kind == "ADR" for item in bundle.items))

    def test_Bundle_AmbiguousAdr_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _write(project, "docs/adr/0017-a.md", "# A\n")
            _write(project, "docs/adr/0017-b.md", "# B\n")
            with self.assertRaises(KnowledgeError) as caught:
                retrievallib.assemble(project, adr_refs=["0017"])
            self.assertEqual(caught.exception.code, "KNOWLEDGE_TARGET_UNSUPPORTED")

    def test_Bundle_MissingFiles_StillWorks(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = retrievallib.assemble(Path(directory))
            self.assertEqual(bundle.items, [])
            self.assertIn("0 item", bundle.render())

    def test_Bundle_FocusEscape_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KnowledgeError) as caught:
                retrievallib.assemble(Path(directory), focus=["../../escape"])
            self.assertEqual(caught.exception.code, "KNOWLEDGE_BAD_LOCATOR")

    def test_Bundle_CanonicalOutranksCandidates(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seed(project)
            storelib.append(project, capture(
                project=str(project), agent="opencode", session="s",
                origin_type="manual", kind="PROJECT_RULE",
                claim="A claimed rule."))
            bundle = retrievallib.assemble(project)
            kinds = [item.kind for item in bundle.items]
            self.assertLess(kinds.index("AGENTS.md"), kinds.index("candidate"))
            notes = [item for item in bundle.items if item.kind == "candidate"]
            self.assertTrue(notes)
            self.assertTrue(all(item.label == "UNVERIFIED CANDIDATE" for item in notes))

    def test_Bundle_TerminalCandidatesExcluded(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            stored = storelib.append(project, capture(
                project=str(project), agent="opencode", session="s",
                origin_type="manual", kind="PROJECT_RULE", claim="Old rule."))
            storelib.set_status(project, stored["candidate_id"], "REJECTED",
                                actor="tester")
            bundle = retrievallib.assemble(project)
            self.assertEqual([item for item in bundle.items
                              if item.kind == "candidate"], [])

    def test_Budgets_TruncateByRank(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seed(project)
            budgets = retrievallib.Budgets(max_bytes=20)
            bundle = retrievallib.assemble(project, budgets=budgets)
            self.assertLessEqual(bundle.total_bytes, 20)
            self.assertGreater(bundle.dropped, 0)

    def test_Recall_WithoutProvider_DegradedButDeterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seed(project)
            bundle = retrievallib.assemble(project, recall="retry policy")
            self.assertTrue(bundle.items)
            self.assertFalse(bundle.recall["fulfilled"])
            self.assertIn("recall unavailable", bundle.render())


class RetrieveCliTest(LifecycleTestCase):
    def knowledge(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli("knowledge", *args)

    def test_Retrieve_FocusedBundle_Json(self):
        (self.project / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        (self.project / "src").mkdir(exist_ok=True)
        (self.project / "src" / "AI_CONTEXT.md").write_text("# Src\n", encoding="utf-8")
        completed = self.knowledge("retrieve", "--focus", "src/app.py", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        locators = [item["locator"] for item in payload["items"]]
        self.assertIn("AGENTS.md", locators)
        self.assertIn("src/AI_CONTEXT.md", locators)
        self.assertTrue(all("label" in item for item in payload["items"]))


if __name__ == "__main__":
    unittest.main()