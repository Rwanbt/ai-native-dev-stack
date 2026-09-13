"""Machine lifecycle: what a global install owns, and how it is reversed.

The installer wrote into six harness configurations and several skill trees
without recording what it had written, so no automatic uninstall existed and a
user could not tell an AI Native file from their own. These tests pin the
record and the reversal rule: recorded and unmodified assets are removed,
user files and user-modified assets are preserved, and a dry run changes
nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STACK = Path(__file__).resolve().parents[2]
INSTALL = STACK / "scripts" / "install_agents.py"


def _run(home: Path, *args: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    for name in ("OBSIDIAN_VAULT", "OBSIDIAN_PROJECT_SLUG"):
        environment.pop(name, None)
    return subprocess.run([sys.executable, str(INSTALL), "--home", str(home), *args],
                          capture_output=True, text=True, env=environment)


class MachineLifecycle(unittest.TestCase):

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="machine-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.home, ignore_errors=True))
        completed = _run(self.home)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def manifest(self) -> dict:
        return json.loads((self.home / ".ai-native" / "machine.json")
                          .read_text(encoding="utf-8"))

    def test_the_install_records_what_it_wrote(self):
        record = self.manifest()
        kinds = {asset["kind"] for asset in record["assets"]}
        self.assertTrue({"link", "block", "rendered"} <= kinds, kinds)
        self.assertGreater(len(record["assets"]), 20)
        # Schema 2 adds the repair fields (heading, vault/slug, template,
        # stack_root); schema-1 manifests stay readable.
        self.assertEqual(record["schema_version"], 2)

    def test_a_dry_run_changes_nothing(self):
        manifest = (self.home / ".ai-native" / "machine.json").read_bytes()
        claude = (self.home / ".claude" / "CLAUDE.md").read_bytes()
        completed = _run(self.home, "--uninstall", "--dry-run")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual((self.home / ".ai-native" / "machine.json").read_bytes(), manifest)
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_bytes(), claude)

    def test_user_files_survive_the_uninstall(self):
        user_skill = self.home / ".claude" / "skills" / "my-own-skill" / "SKILL.md"
        user_skill.parent.mkdir(parents=True, exist_ok=True)
        user_skill.write_text("# mine\n", encoding="utf-8")
        notes = self.home / ".claude" / "MY-NOTES.md"
        notes.write_text("# private notes\n", encoding="utf-8")

        completed = _run(self.home, "--uninstall")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(user_skill.is_file())
        self.assertTrue(notes.is_file())
        self.assertFalse((self.home / ".ai-native" / "machine.json").exists())

    def test_a_user_modified_rendered_file_is_preserved(self):
        target = self.home / ".config" / "opencode" / "plugins" / "ai-native-dev-stack.ts"
        target.write_text("// edited by the user\n", encoding="utf-8")
        completed = _run(self.home, "--uninstall")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(target.is_file())
        self.assertIn("PRESERVE", completed.stdout)

    def test_the_second_uninstall_reports_nothing_recorded(self):
        _run(self.home, "--uninstall")
        completed = _run(self.home, "--uninstall")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("nothing is recorded", completed.stdout)

    def test_a_malformed_manifest_is_refused(self):
        (self.home / ".ai-native" / "machine.json").write_text("{not json", encoding="utf-8")
        completed = _run(self.home, "--uninstall")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("ERROR", completed.stderr)


if __name__ == "__main__":
    unittest.main()