from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.mv00.semantic_egress import SemanticEgress, inspect


class SemanticEgressTests(unittest.TestCase):
    def write_json(self, root: Path, relative: str, value: object) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_plugin_is_none(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect(Path(directory))
        self.assertEqual(SemanticEgress.NONE, report.semantic_background_egress)
        self.assertFalse(report.sensitive_semantic_available)

    def test_enabled_plugin_without_observation_stays_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_json(root, ".obsidian/plugins/smart-connections/manifest.json", {"version": "4.7.2"})
            self.write_json(root, ".obsidian/plugins/smart-connections/data.json", {"token": "never expose", "provider": "local"})
            self.write_json(root, ".obsidian/community-plugins.json", ["smart-connections"])
            report = inspect(root)
        self.assertTrue(report.plugin_present)
        self.assertTrue(report.plugin_enabled)
        self.assertEqual("4.7.2", report.plugin_version)
        self.assertEqual(("provider", "token"), report.setting_keys)
        self.assertEqual(SemanticEgress.UNKNOWN, report.semantic_background_egress)
        self.assertFalse(report.sensitive_semantic_available)


if __name__ == "__main__":
    unittest.main()
