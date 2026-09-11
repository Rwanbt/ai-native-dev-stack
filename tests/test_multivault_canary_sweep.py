import tempfile
import unittest
from pathlib import Path

from ainative.multivault.canary_sweep import (
    EXIT_COMPLETE_CLEAN,
    EXIT_INCOMPLETE,
    EXIT_LEAK,
    INFRASTRUCTURE_UNAVAILABLE,
    STORE_LOCATION_UNKNOWN,
    CanarySurface,
    marker_for,
    run_canary_sweep,
)


class CanarySweepTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.domains = {}
        for domain in ("personal", "company-a", "company-b"):
            path = self.root / domain
            path.mkdir()
            self.domains[domain] = path
        self.surfaces = tuple(
            CanarySurface(domain, domain, "filesystem", path) for domain, path in self.domains.items()
        )

    def tearDown(self):
        self._temporary.cleanup()

    def test_complete_clean_sweep_returns_zero(self):
        report = run_canary_sweep(self.surfaces, nonce="n1")
        self.assertEqual(EXIT_COMPLETE_CLEAN, report.exit_code)
        self.assertEqual((), report.leaks)
        self.assertIn("personal", report.scanned)

    def test_real_leak_is_detected_and_returns_one(self):
        foreign = self.domains["company-b"] / "stolen.txt"
        foreign.write_bytes(marker_for("n2", "personal"))
        report = run_canary_sweep(self.surfaces, nonce="n2")
        self.assertEqual(EXIT_LEAK, report.exit_code)
        self.assertTrue(any("company-b" == leak.surface for leak in report.leaks))

    def test_unknown_store_location_is_incomplete_and_returns_two(self):
        surfaces = self.surfaces + (CanarySurface("company-a", "company-a-memory", "store", None),)
        report = run_canary_sweep(surfaces, nonce="n3")
        self.assertEqual(EXIT_INCOMPLETE, report.exit_code)
        self.assertTrue(any(finding.code == STORE_LOCATION_UNKNOWN for finding in report.incomplete))

    def test_missing_surface_is_incomplete_and_returns_two(self):
        surfaces = self.surfaces + (
            CanarySurface("company-b", "company-b-vault", "vault", self.root / "missing"),
        )
        report = run_canary_sweep(surfaces, nonce="n4")
        self.assertEqual(EXIT_INCOMPLETE, report.exit_code)
        self.assertTrue(any(finding.code == INFRASTRUCTURE_UNAVAILABLE for finding in report.incomplete))

    def test_leak_outranks_incomplete(self):
        foreign = self.domains["company-b"] / "stolen.txt"
        foreign.write_bytes(marker_for("n5", "personal"))
        surfaces = self.surfaces + (CanarySurface("company-a", "unknown", "store", None),)
        report = run_canary_sweep(surfaces, nonce="n5")
        self.assertEqual(EXIT_LEAK, report.exit_code)

    def test_planted_markers_are_cleaned_after_a_clean_sweep(self):
        run_canary_sweep(self.surfaces, nonce="n6")
        remaining = [path for path in self.root.rglob(".ainative-canary-*")]
        self.assertEqual([], remaining)

    def test_report_carries_the_guarded_honesty_statement(self):
        report = run_canary_sweep(self.surfaces, nonce="n7")
        self.assertIn("does not resist a hostile same-OS-user", report.assurance)