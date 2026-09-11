from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.mv00.harness_autoload import inventory


class HarnessAutoloadTests(unittest.TestCase):
    def test_inventory_reports_names_without_reading_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("secret", encoding="utf-8")
            (root / ".codex").mkdir()
            (root / ".codex" / "mcp.json").write_text("secret", encoding="utf-8")
            report = inventory(root)
        self.assertEqual((".codex/mcp.json", "AGENTS.md"), report.surfaces)
        self.assertEqual("UNKNOWN", report.disable_control)
        self.assertFalse(report.sensitive_harness_available)


if __name__ == "__main__":
    unittest.main()
