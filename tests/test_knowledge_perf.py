"""K9 performance budgets: generous guardrails, not benchmarks.

These assert orders of magnitude on a small store (capture p50,
bundle assembly, consolidation) so a future regression screams
instead of whispering. Bounds are deliberately loose to stay green
on slow CI; tighten only from measured distributions (plan Phase K9:
measure before hard limits).
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from ainative.knowledge import consolidation as consolidationlib
from ainative.knowledge import evidence as evidencelib
from ainative.knowledge import retrieval as retrievallib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib
from ainative.knowledge.candidate import capture


def _seeded(project: Path, count: int = 20) -> None:
    (project / "AGENTS.md").write_bytes(b"# Rules\n")
    for index in range(count):
        stored = storelib.append(project, capture(
            project=str(project), agent="opencode", session="s",
            origin_type="user_correction", kind="PROJECT_RULE",
            claim=f"Rule number {index} about explicit budgets."))
        reviewlib.classify_candidate(project, stored["candidate_id"],
                                     kind="PROJECT_RULE", actor="tester")
        evidencelib.add_evidence(project, stored["candidate_id"],
                                 {"type": "USER_CONFIRMATION", "locator": "s"},
                                 actor="tester")


class PerformanceBudgetTest(unittest.TestCase):
    def test_Capture_TwentyCandidates_UnderTenSeconds(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            started = time.monotonic()
            _seeded(project, 20)
            self.assertLess(time.monotonic() - started, 10.0)

    def test_Retrieve_Bundle_UnderTenSeconds(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seeded(project, 20)
            started = time.monotonic()
            bundle = retrievallib.assemble(project, focus=["."])
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 10.0)
            self.assertLessEqual(bundle.total_bytes, 65536)

    def test_Consolidate_TwentyCandidates_UnderSixtySeconds(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _seeded(project, 20)
            started = time.monotonic()
            report = consolidationlib.consolidate(project)
            self.assertLess(time.monotonic() - started, 60.0)
            self.assertEqual(len(report["recommendations"]), 20)


if __name__ == "__main__":
    unittest.main()