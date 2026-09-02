import json
import subprocess
import sys
import tempfile
import unittest


class CliTests(unittest.TestCase):
    def test_work_new_then_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, "-m", "ainative_workplane", "work", "new", directory, "--artifact", "tasks={\"done\":false}"]
            created = json.loads(subprocess.check_output(command, text=True))
            self.assertEqual(1, created["revision"])
            validated = json.loads(subprocess.check_output([sys.executable, "-m", "ainative_workplane", "work", "validate", directory], text=True))
            self.assertEqual(created, validated)
