"""PR9 security gate: cross-project isolation, leakage target zero."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import scope as scopelib
from ainative.knowledge import semantic as semanticlib


def _note(directory: Path, name: str, content: str = "note body") -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _registry(root: Path, slug: str, shared: dict | None = None) -> scopelib.ProjectRegistry:
    return scopelib.ProjectRegistry(project_root=root, project_slug=slug,
                                    shared_roots=shared or {})


class FakeSemantic:
    name = "fake-semantic"

    def __init__(self, hits: list, crash: bool = False) -> None:
        self.hits = hits
        self.crash = crash

    def capabilities(self) -> dict:
        return {"search": True}

    def search(self, query: str, scope: str, limit: int) -> list:
        if self.crash:
            raise ConnectionError("index offline")
        return self.hits[:limit]

    def health(self) -> dict:
        return {"available": not self.crash}

    def metadata(self) -> dict:
        return {"execution_scope": "test", "data_egress": "none",
                "project_filtering": "none",
                "authority_ceiling": "INFORMATIVE_RESEARCH"}


class CrossProjectTest(unittest.TestCase):
    def test_ProjectAResult_InBQuery_Dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            secret = _note(base / "proj-a", "memory.md", "USE_PROD_SECRET_X")
            _note(base / "proj-b", "memory.md", "unrelated")
            provider = FakeSemantic([{"locator": "memory.md",
                                      "source_path": str(secret),
                                      "excerpt": "USE_PROD_SECRET_X",
                                      "scope": "project/proj-b"}])
            sources, report = semanticlib.search_scoped(
                provider, "prod secret", registry=_registry(base / "proj-b", "proj-b"))
            self.assertEqual(sources, [])
            self.assertEqual(len(report["dropped"]), 1)

    def test_OutsideNote_ClaimingBMetadata_Dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            outsider = _note(base / "elsewhere", "note.md", "A secret")
            provider = FakeSemantic([{"locator": "note.md",
                                      "source_path": str(outsider),
                                      "excerpt": "A secret",
                                      "scope": "project/proj-b"}])
            sources, _ = semanticlib.search_scoped(
                provider, "secret", registry=_registry(base / "proj-b", "proj-b"))
            self.assertEqual(sources, [])

    def test_UnresolvablePath_Dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            provider = FakeSemantic([{"locator": "ghost.md",
                                      "source_path": str(base / "nope.md"),
                                      "excerpt": "ghost"}])
            sources, report = semanticlib.search_scoped(
                provider, "ghost", registry=_registry(base / "proj-b", "proj-b"))
            self.assertEqual(sources, [])
            self.assertIn("resolv", report["dropped"][0]["reason"])

    def test_RelativePath_Dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _note(project, "memory.md", "body")
            provider = FakeSemantic([{"locator": "memory.md",
                                      "source_path": "memory.md",
                                      "excerpt": "body"}])
            sources, _ = semanticlib.search_scoped(
                provider, "body", registry=_registry(project, "demo"))
            self.assertEqual(sources, [])

    def test_SharedWithoutConfig_Dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shared = _note(base / "shared", "guide.md", "shared guide")
            provider = FakeSemantic([{"locator": "guide.md",
                                      "source_path": str(shared),
                                      "excerpt": "shared guide"}])
            sources, _ = semanticlib.search_scoped(
                provider, "guide", registry=_registry(base / "proj-b", "proj-b"))
            self.assertEqual(sources, [])

    def test_SharedConfiguredAndAllowed_CappedInclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shared = _note(base / "shared", "guide.md", "shared guide")
            registry = _registry(base / "proj-b", "proj-b",
                                 shared={"team": base / "shared"})
            provider = FakeSemantic([{"locator": "guide.md",
                                      "source_path": str(shared),
                                      "excerpt": "shared guide"}])
            sources, _ = semanticlib.search_scoped(
                provider, "guide", registry=registry, shared_allowed=True)
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["scope"], "global/team")
            self.assertEqual(sources[0]["authority_domain"],
                             "HISTORICAL_OBSERVATION")

    def test_ZeroLeakage_Sweep(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            in_b = _note(base / "proj-b", "memory.md", "b body")
            _note(base / "proj-a", "memory.md", "USE_PROD_SECRET_X")
            _note(base / "shared", "guide.md", "guide")
            provider = FakeSemantic([
                {"locator": "memory.md",
                 "source_path": str(base / "proj-a" / "memory.md"),
                 "excerpt": "USE_PROD_SECRET_X"},
                {"locator": "memory.md", "source_path": str(in_b),
                 "excerpt": "b body"},
                {"locator": "guide.md",
                 "source_path": str(base / "shared" / "guide.md"),
                 "excerpt": "guide"},
                {"locator": "ghost.md",
                 "source_path": str(base / "missing.md"), "excerpt": "ghost"},
            ])
            sources, report = semanticlib.search_scoped(
                provider, "body", registry=_registry(base / "proj-b", "proj-b"),
                limit=10)
            self.assertEqual([item["locator"] for item in sources],
                             ["memory.md"])
            self.assertTrue(all(item["scope"] == "project/proj-b"
                                for item in sources))
            blob = str(sources)
            self.assertNotIn("USE_PROD_SECRET_X", blob)
            self.assertEqual(len(report["dropped"]), 3)

    def test_SameBasename_NoSurnameLeak(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _note(base / "proj-a", "memory.md", "A secret")
            in_b = _note(base / "proj-b", "memory.md", "B body")
            provider = FakeSemantic([
                {"locator": "memory.md",
                 "source_path": str(base / "proj-a" / "memory.md"),
                 "excerpt": "A secret"},
                {"locator": "memory.md", "source_path": str(in_b),
                 "excerpt": "B body"},
            ])
            sources, _ = semanticlib.search_scoped(
                provider, "memory", registry=_registry(base / "proj-b", "proj-b"),
                limit=10)
            self.assertEqual(len(sources), 1)
            self.assertNotIn("A secret", str(sources))

    def test_SymlinkEscape_Dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = _note(base / "outside", "secret.md", "outside secret")
            link = base / "proj-b" / "link.md"
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(str(target), str(link))
            except OSError:
                self.skipTest("symlinks unavailable")
            provider = FakeSemantic([{"locator": "link.md",
                                      "source_path": str(link),
                                      "excerpt": "outside secret"}])
            sources, report = semanticlib.search_scoped(
                provider, "secret", registry=_registry(base / "proj-b", "proj-b"))
            self.assertEqual(sources, [])
            self.assertTrue(report["dropped"])

    def test_FinerClaimedScope_Downgraded(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            note = _note(project, "memory.md", "body")
            provider = FakeSemantic([{"locator": "memory.md",
                                      "source_path": str(note),
                                      "excerpt": "body",
                                      "scope": "module/payment"}])
            sources, _ = semanticlib.search_scoped(
                provider, "body", registry=_registry(project, "demo"))
            self.assertEqual(sources[0]["scope"], "project/demo")


class ProviderContractTest(unittest.TestCase):
    def test_Noop_DocumentsAbsence(self):
        provider = semanticlib.NoopSemanticProvider()
        self.assertEqual(provider.search("x", "y", 5), [])
        self.assertFalse(provider.health()["available"])
        self.assertFalse(provider.capabilities()["search"])

    def test_CrashingBackend_Degrades(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeSemantic([], crash=True)
            sources, report = semanticlib.search_scoped(
                provider, "x", registry=_registry(Path(directory), "demo"))
            self.assertEqual((sources, report["fulfilled"] if "fulfilled" in report else None),
                             ([], None))
            self.assertIn("fault", report["reason"])

    def test_NonListBackend_Degrades(self):
        class Bad:
            name = "bad"

            def search(self, query, scope, limit):
                return {"not": "a list"}

        with tempfile.TemporaryDirectory() as directory:
            sources, report = semanticlib.search_scoped(
                Bad(), "x", registry=_registry(Path(directory), "demo"))
            self.assertEqual(sources, [])

    def test_CeilingCapsClaims(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            note = _note(project, "memory.md", "body")
            provider = FakeSemantic([{"locator": "memory.md",
                                      "source_path": str(note),
                                      "excerpt": "body",
                                      "authority_domain": "ENGINEERING_POLICY"}])
            sources, _ = semanticlib.search_scoped(
                provider, "body", registry=_registry(project, "demo"),
                ceiling="UNTRUSTED")
            self.assertEqual(sources[0]["authority_domain"], "UNTRUSTED")


if __name__ == "__main__":
    unittest.main()
