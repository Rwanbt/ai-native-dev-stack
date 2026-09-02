import tempfile
import unittest
from pathlib import Path

from ainative_workplane.integrations import collect_findings, memory_summary
from ainative_workplane.metrics import PilotMetrics


class IntegrationMetricsTests(unittest.TestCase):
    def test_integrations_are_read_only_and_memory_summary_is_compact(self):
        findings = collect_findings(graphify=[{"code": "CYCLE", "message": "cycle"}], anti_debt=[{"code": "TODO", "message": "debt"}])
        self.assertEqual(("graphify", "anti-debt"), tuple(item.source for item in findings))
        summary = memory_summary(work_uid="work-1", problem="p", result="r", decisions=["d"])
        self.assertEqual(["d"], summary["important_decisions"])
        self.assertNotIn("verdict", summary)

    def test_metrics_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.json"
            PilotMetrics(reruns=2).write(path)
            self.assertIn('"reruns":2', path.read_text(encoding="utf-8"))
