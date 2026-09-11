import sys
import unittest

from scripts.mv00.containment_probe import run_probe


class ContainmentProbeTests(unittest.TestCase):
    def test_supervisor_loss_kills_detached_descendants_on_windows(self):
        if sys.platform != "win32":
            self.skipTest("Windows Job Object probe targets win32")
        report = run_probe(timeout=20.0)
        self.assertEqual("VERIFIED", report["result"], report.get("reason"))
        self.assertTrue(report["kill_on_close"])
        self.assertTrue(report["detached_descendant_killed"])
        self.assertTrue(report["breakaway_denied"])