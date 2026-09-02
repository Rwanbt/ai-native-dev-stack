import tempfile
import unittest
from pathlib import Path

from ainative_workplane.convergence import append_convergence, converge, stall_fingerprint
from ainative_workplane.traceability import analyze


class ConvergenceHistoryTests(unittest.TestCase):
    def test_stall_fingerprint_is_deterministic_and_history_is_append_only(self):
        verdict = converge(analyze([], [], [], []), [{"uid": "run-1", "status": "FAIL"}])
        self.assertEqual(verdict.fingerprint, stall_fingerprint(verdict.gaps))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "convergence.jsonl"
            append_convergence(path, verdict, work_uid="work-1", engine_version="1")
            append_convergence(path, verdict, work_uid="work-1", engine_version="1")
            self.assertEqual(2, len(path.read_text(encoding="utf-8").splitlines()))
