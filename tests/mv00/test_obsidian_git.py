from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.mv00.obsidian_git import WriterState, inspect


class ObsidianGitTests(unittest.TestCase):
    def write_json(self, root: Path, name: str, value: object) -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_absent_plugin_is_inactive(self):
        with tempfile.TemporaryDirectory() as directory:
            report = inspect(Path(directory))
        self.assertEqual(WriterState.INACTIVE, report.concurrent_writer)

    def test_enabled_plugin_is_unknown_not_inactive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_json(root, ".obsidian/plugins/obsidian-git/manifest.json", {"version": "2.39.0"})
            self.write_json(root, ".obsidian/plugins/obsidian-git/data.json", {"autoPushInterval": 60})
            self.write_json(root, ".obsidian/community-plugins.json", ["obsidian-git"])
            report = inspect(root)
        self.assertEqual(WriterState.UNKNOWN, report.concurrent_writer)
        self.assertFalse(report.sensitive_sync_available)
        self.assertEqual(("autoPushInterval",), report.setting_keys)


if __name__ == "__main__":
    unittest.main()
