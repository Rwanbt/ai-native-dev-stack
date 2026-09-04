import unittest

from scripts.workplane_harness_matrix import run


class HarnessMatrixTests(unittest.TestCase):
    def test_two_local_harnesses_complete_five_items(self):
        result = run()
        self.assertEqual(5, result["direct_api"])
        self.assertEqual(5, result["cli_facade"])
        self.assertFalse(result["external_harness"])
