"""K5b gates: provider contracts, graph file adapter, degraded recall."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import providers as providerslib
from ainative.knowledge import retrieval as retrievallib
from ainative.knowledge import store as storelib
from ainative.knowledge.candidate import capture


class FakeGraph:
    name = "fake-graph"

    def __init__(self, peers: dict, fail: bool = False) -> None:
        self.peers = peers
        self.fail = fail

    def probe(self) -> str:
        return "available (fake)"

    def neighbors(self, path: str, *, max_neighbors: int = 10):
        if self.fail:
            raise RuntimeError("graph exploded")
        return [providerslib.GraphNeighbor(path=peer, distance=1)
                for peer in self.peers.get(path, [])[:max_neighbors]]


class FakeSemantic:
    name = "fake-semantic"

    def __init__(self, hits=None, fail: bool = False) -> None:
        self.hits = hits or []
        self.fail = fail

    def probe(self) -> str:
        return "available (fake)"

    def search(self, query: str, *, limit: int = 5):
        if self.fail:
            raise RuntimeError("index offline")
        return self.hits[:limit]


def _graph_json() -> dict:
    return {"nodes": [{"id": "src/app.py"}, {"id": "src/db.py"},
                      {"id": "src/auth.py"}],
            "edges": [{"source": "src/app.py", "target": "src/db.py"},
                      {"from": "src/app.py", "to": "src/auth.py",
                       "type": "calls"}]}


class GraphFileTest(unittest.TestCase):
    def test_GraphFile_NeighborsBfs(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "graphify-out").mkdir()
            (project / "graphify-out" / "graph.json").write_text(
                json.dumps(_graph_json()), encoding="utf-8")
            provider = providerslib.GraphFileProvider(project)
            self.assertTrue(provider.available)
            neighbors = provider.neighbors("src/app.py")
            self.assertEqual({item.path for item in neighbors},
                             {"src/db.py", "src/auth.py"})
            self.assertTrue(provider.probe().startswith("available"))

    def test_GraphFile_Missing_Degrades(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = providerslib.GraphFileProvider(Path(directory))
            self.assertFalse(provider.available)
            self.assertIn("not present", provider.probe())
            self.assertEqual(provider.neighbors("x.py"), [])

    def test_GraphFile_Malformed_Degrades(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "graphify-out").mkdir()
            (project / "graphify-out" / "graph.json").write_text(
                "{nope", encoding="utf-8")
            provider = providerslib.GraphFileProvider(project)
            self.assertFalse(provider.available)
            bundle = retrievallib.assemble(
                project, providers=providerslib.RetrievalProviders(graph=provider))
            self.assertEqual(bundle.items, [])


class ProviderRankingTest(unittest.TestCase):
    def test_Structural_HintsListedAndBonusApplied(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            storelib.append(project, capture(
                project=str(project), agent="opencode", session="s",
                origin_type="manual", kind="MODULE_INVARIANT",
                claim="Vault cache needs a TTL.", module="vault"))
            graph = FakeGraph({"src/app.py": ["vault/cache.py"]})
            providers = providerslib.RetrievalProviders(graph=graph)
            bundle = retrievallib.assemble(project, focus=["src/app.py"],
                                           providers=providers)
            self.assertIn("vault/cache.py", bundle.structural["hints"])
            notes = [item for item in bundle.items if item.kind == "candidate"]
            self.assertTrue(notes)
            plain = retrievallib.assemble(project, focus=["src/app.py"])
            boosted = [item for item in bundle.items if item.kind == "candidate"][0]
            unboosted = [item for item in plain.items if item.kind == "candidate"][0]
            self.assertGreater(boosted.score, unboosted.score)

    def test_Structural_Fault_Degrades(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            providers = providerslib.RetrievalProviders(graph=FakeGraph({}, fail=True))
            bundle = retrievallib.assemble(project, providers=providers)
            self.assertIn("unavailable", bundle.structural)
            self.assertEqual(bundle.items, [])

    def test_Semantic_RecallFulfilledBelowCanonicalFloor(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "AGENTS.md").write_bytes(b"# Rules\n")
            hits = [providerslib.SemanticHit(locator="vault/note.md", score=0.99,
                                             excerpt="retry wisdom")]
            providers = providerslib.RetrievalProviders(semantic=FakeSemantic(hits))
            bundle = retrievallib.assemble(project, recall="retry",
                                           providers=providers)
            self.assertTrue(bundle.recall["fulfilled"])
            self.assertEqual(bundle.recall["provider"], "fake-semantic")
            notes = [item for item in bundle.items if item.kind == "semantic"]
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].label, "RETRIEVED NOTE")
            agents = [item for item in bundle.items if item.kind == "AGENTS.md"][0]
            self.assertLess(notes[0].score, agents.score)

    def test_Semantic_ExternalLabelPreserved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            hits = [providerslib.SemanticHit(locator="https://example.test/x",
                                             score=0.5, excerpt="ext",
                                             external=True)]
            providers = providerslib.RetrievalProviders(semantic=FakeSemantic(hits))
            bundle = retrievallib.assemble(project, recall="x", providers=providers)
            self.assertEqual(bundle.items[0].label, "EXTERNAL CONTENT")

    def test_Semantic_Fault_Degrades(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "AGENTS.md").write_bytes(b"# Rules\n")
            providers = providerslib.RetrievalProviders(
                semantic=FakeSemantic(fail=True))
            bundle = retrievallib.assemble(project, recall="x", providers=providers)
            self.assertFalse(bundle.recall["fulfilled"])
            self.assertIn("fake-semantic", bundle.recall["reason"])
            self.assertTrue(any(item.kind == "AGENTS.md" for item in bundle.items))


if __name__ == "__main__":
    unittest.main()