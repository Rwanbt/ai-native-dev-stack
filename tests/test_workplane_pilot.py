import unittest

from scripts.workplane_pilot import run


class PilotTests(unittest.TestCase):
    def test_five_work_item_local_pilot(self):
        report = run()
        self.assertEqual(5, report["work_items"])
        self.assertEqual(5, report["completed"])
        self.assertFalse(report["external_harness"])
