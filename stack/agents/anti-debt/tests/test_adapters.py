#!/usr/bin/env python3
"""Test runner for validate_adapters.py."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(r"D:\App\ai-native-dev-stack\stack\agents\anti-debt\tools")
sys.path.insert(0, str(TOOLS))

import validate_adapters  # noqa: E402

ROOT = Path(r"D:\App\ai-native-dev-stack\stack\agents\anti-debt")
ADAPTERS = ROOT / "adapters"


class TestValidateAdapters(unittest.TestCase):
    def test_covered_tools_extracts_names(self):
        snippet = {"permissions": {"allow": ["Bash(ruff:*)", "Bash(trufflehog:*)", "Bash(osv-scanner:*)"]}}
        tools = validate_adapters._covered_tools(snippet)
        self.assertEqual(tools, {"ruff", "trufflehog", "osv-scanner"})

    def test_covered_tools_handles_wildcards(self):
        snippet = {"permissions": {"allow": ["Bash(python3:*)", "Bash(cargo:*)"]}}
        tools = validate_adapters._covered_tools(snippet)
        self.assertIn("python3", tools)
        self.assertIn("cargo", tools)

    def test_perms_format_ok(self):
        ok, msg = validate_adapters._is_perms_format_ok({"permissions": {"allow": ["Bash(ruff:*)"]}})
        self.assertTrue(ok, msg)
        self.assertEqual(msg, "")

    def test_perms_format_missing_allow(self):
        ok, msg = validate_adapters._is_perms_format_ok({"permissions": {}})
        self.assertFalse(ok)
        self.assertIn("allow", msg)

    def test_perms_format_empty_allow(self):
        ok, msg = validate_adapters._is_perms_format_ok({"permissions": {"allow": []}})
        self.assertFalse(ok)
        self.assertIn("empty", msg)

    def test_perms_format_no_permissions(self):
        ok, msg = validate_adapters._is_perms_format_ok({})
        self.assertFalse(ok)

    def test_perms_format_non_string_entry(self):
        ok, msg = validate_adapters._is_perms_format_ok({"permissions": {"allow": [123]}})
        self.assertFalse(ok)

    def test_mentioned_skills(self):
        text = "Look at skills/debt-scan/SKILL.md and skills/critic/SKILL.md for more info."
        skills = validate_adapters._mentioned_skills(text)
        self.assertEqual(skills, {"debt-scan", "critic"})

    def test_mentioned_skills_empty(self):
        self.assertEqual(validate_adapters._mentioned_skills("no skill mentions here"), set())

    def test_main_real_adapters(self):
        """Run validator on the actual adapters directory."""
        result = subprocess.run(
            [sys.executable, str(TOOLS / "validate_adapters.py")],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")
        report = json.loads(result.stdout)
        # claude-code and minimax-code should be OK
        adapter_names = {a["adapter"] for a in report["adapters"]}
        self.assertIn("claude-code", adapter_names)
        self.assertIn("minimax-code", adapter_names)
        # generic has manual install, should be ok
        for a in report["adapters"]:
            if a["adapter"] == "generic":
                self.assertTrue(a["ok"], f"generic should be ok (manual install): {a['issues']}")

    def test_main_synthetic_adapter_with_error(self):
        """Create a synthetic adapter with a broken snippet and check it errors."""
        with tempfile.TemporaryDirectory() as tmp:
            # Adapters dir with a broken adapter
            ad = Path(tmp) / "broken-adapter"
            ad.mkdir()
            (ad / "settings-snippet.json").write_text("{ not json", encoding="utf-8")
            (ad / "README.md").write_text("# broken", encoding="utf-8")
            # Mock the ADAPTERS path
            original = validate_adapters.ADAPTERS
            validate_adapters.ADAPTERS = Path(tmp)
            try:
                # Re-run validation
                from io import StringIO
                from contextlib import redirect_stdout
                buf = StringIO()
                with redirect_stdout(buf):
                    rc = validate_adapters.main()
            finally:
                validate_adapters.ADAPTERS = original
            self.assertEqual(rc, 1)  # error exit
            report = json.loads(buf.getvalue())
            self.assertFalse(report["all_ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
