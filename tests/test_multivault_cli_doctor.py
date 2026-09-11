import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative.multivault.authority_store import AuthorityStore


def cli(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ainative.multivault", *arguments],
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
    )


class DoctorContextCliTests(unittest.TestCase):
    def test_doctor_passes_binding_on_a_governed_repository_and_context_stays_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "authority.json"
            AuthorityStore(store_path).replace({"company-a": {"vault": "v", "checkout": "c", "classification": "CONFIDENTIAL"}})
            doctor = cli("doctor", "--store", str(store_path), "--domain", "company-a", "--repo", str(Path.cwd()))
            self.assertIn("PASS\tbinding", doctor.stdout)
            context = cli("context", "--store", str(store_path), "--domain", "company-a")
            self.assertEqual(0, context.returncode)
            self.assertIn("qualification: UNKNOWN", context.stdout)
            self.assertIn("supported: no", context.stdout)

    def test_context_fails_closed_without_a_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "authority.json"
            result = cli("context", "--store", str(store_path), "--domain", "company-a")
            self.assertEqual(1, result.returncode)
            self.assertIn("binding: MISSING", result.stdout)

    def test_doctor_reports_unknown_on_a_corrupt_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "authority.json"
            store_path.write_text("{not json", encoding="utf-8")
            doctor = cli("doctor", "--store", str(store_path), "--domain", "company-a", "--repo", str(Path.cwd()))
            self.assertEqual(1, doctor.returncode)
            self.assertIn("UNKNOWN\tbinding", doctor.stdout)