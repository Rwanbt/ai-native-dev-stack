"""PR8 gates: probe, bounds, ceiling, degradation, project confinement."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ainative.knowledge import graph as graphlib
from ainative.knowledge import planner as plannerlib


def _graph_file(directory: Path, payload: dict) -> Path:
    target = directory / "graphify-out" / "graph.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _sample() -> dict:
    return {
        "directed": True,
        "nodes": [
            {"id": "src_app", "label": "app.py", "source_file": "src/app.py"},
            {"id": "src_db", "label": "db.py", "source_file": "src/db.py"},
            {"id": "evil", "label": "x.py", "source_file": "../../escape.py"},
            {"id": "abs", "label": "y.py", "source_file": "/etc/passwd"},
            {"id": "concept", "label": "SomeConcept"},
        ],
        "links": [
            {"source": "src_app", "target": "src_db",
             "relation": "imports", "weight": 2.0},
            {"source": "src_app", "target": "evil", "relation": "imports",
             "weight": 1.0},
            {"source": "src_app", "target": "abs", "relation": "imports",
             "weight": 1.0},
            {"source": "src_app", "target": "concept", "relation": "mentions",
             "weight": 1.0},
        ],
    }


def _project(directory: str) -> Path:
    project = Path(directory)
    (project / "src" / "app.py").parent.mkdir(parents=True, exist_ok=True)
    (project / "src" / "app.py").write_text("app\n", encoding="utf-8")
    (project / "src" / "db.py").write_text("db\n", encoding="utf-8")
    return project


class ProbeTest(unittest.TestCase):
    def test_MissingFile_Unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = graphlib.FileGraphProvider(Path(directory))
            report = provider.health()
            self.assertFalse(report["available"])
            self.assertIn("absent", provider.probe())
            records, drop = provider.neighbors("src/app.py")
            self.assertEqual((records, drop["reason"] is not None), ([], True))

    def test_MalformedFile_Degraded(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = project / "graphify-out" / "graph.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{nope", encoding="utf-8")
            provider = graphlib.FileGraphProvider(project)
            self.assertFalse(provider.health()["available"])
            records, _ = provider.neighbors("src/app.py")
            self.assertEqual(records, [])

    def test_OversizeFile_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            with mock.patch.object(graphlib, "MAX_GRAPH_BYTES", 10):
                provider = graphlib.FileGraphProvider(project)
                self.assertFalse(provider.health()["available"])

    def test_Healthy_ReportsCounts(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(project)
            report = provider.health()
            self.assertTrue(report["available"])
            self.assertGreaterEqual(report["nodes"], 3)
            self.assertIn("ceiling", provider.probe())


class NeighborhoodTest(unittest.TestCase):
    def test_FocusMatch_ByPathAndBasename(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(project)
            by_path, _ = provider.neighbors("src/app.py")
            by_base, _ = provider.neighbors("other/app.py")
            self.assertTrue(any(entry["path"].name == "db.py" for entry in by_path))
            self.assertTrue(any(entry["path"].name == "db.py" for entry in by_base))

    def test_OutsideRoot_Dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(project)
            records, report = provider.neighbors("src/app.py")
            names = {entry["path"].name for entry in records}
            self.assertNotIn("x.py", names)
            self.assertNotIn("passwd", names)
            self.assertGreaterEqual(report["dropped_outside_root"], 2)

    def test_ConceptNode_Skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(project)
            records, _ = provider.neighbors("src/app.py")
            self.assertTrue(all(entry["path"].is_file() for entry in records))

    def test_MinWeight_Filters(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(project)
            records, _ = provider.neighbors("src/app.py", min_weight=1.5)
            self.assertEqual([entry["path"].name for entry in records], ["db.py"])


class CeilingTest(unittest.TestCase):
    def test_CapDomain_LowersNeverRaises(self):
        self.assertEqual(graphlib.cap_domain("ENGINEERING_POLICY",
                                             "INFORMATIVE_RESEARCH"),
                         "INFORMATIVE_RESEARCH")
        self.assertEqual(graphlib.cap_domain("UNTRUSTED", "INFORMATIVE_RESEARCH"),
                         "UNTRUSTED")
        self.assertEqual(graphlib.cap_domain("BOGUS", "INFORMATIVE_RESEARCH"),
                         "UNTRUSTED")

    def test_StructuralSources_CappedTierC(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(project)
            sources, report = graphlib.structural_sources(provider, "src/app.py")
            self.assertTrue(sources)
            self.assertTrue(all(item["tier"] == "C" for item in sources))
            self.assertTrue(all(item["authority_domain"] == "INFORMATIVE_RESEARCH"
                                for item in sources))
            self.assertGreaterEqual(report["returned"], 1)

    def test_RaisedCeiling_Honored(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            provider = graphlib.FileGraphProvider(
                project, authority_ceiling="ENGINEERING_POLICY")
            sources, _ = graphlib.structural_sources(provider, "src/app.py")
            self.assertTrue(all(item["authority_domain"] == "IMPLEMENTATION_FACT"
                                for item in sources))


class PlannerIntegrationTest(unittest.TestCase):
    def test_BudgetDrop_HitsTierCOnly(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _graph_file(project, _sample())
            (project / "AGENTS.md").write_bytes(b"# Rules\n")
            provider = graphlib.FileGraphProvider(project)
            sources, _ = graphlib.structural_sources(provider, "src/app.py")
            bundle = plannerlib.plan(
                [{"kind": "agents", "locator": "AGENTS.md", "scope": "project",
                  "excerpt": "# Rules\n"}, *sources],
                budgets=plannerlib.Budgets(max_bytes=8, max_items=64))
            self.assertEqual([item.source for item in bundle.items],
                             ["AGENTS.md"])
            self.assertEqual({entry["locator"] for entry in bundle.dropped},
                             {"src/db.py"})

    def test_InvalidDomainClaim_Dropped(self):
        bundle = plannerlib.plan([{"kind": "code", "locator": "x",
                                   "scope": "project", "excerpt": "x",
                                   "authority_domain": "BOGUS"}])
        self.assertEqual(bundle.items, [])
        self.assertEqual(bundle.dropped[0]["reason"],
                         "invalid authority domain")


if __name__ == "__main__":
    unittest.main()
