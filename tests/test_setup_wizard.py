"""`ainative setup` — the guided first run, and its non-interactive form.

The wizard composes the dedicated commands; these tests pin the composition:
without a terminal it refuses unless the choices were passed as flags, every
step is skippable, and whatever it does is exactly what `init` and
`machine init` do — no hidden step, no implicit mutation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STACK = Path(__file__).resolve().parents[1]


def _run(project: Path, home: Path, *args: str,
         git: bool = True) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    for name in ("OBSIDIAN_VAULT", "OBSIDIAN_PROJECT_SLUG"):
        environment.pop(name, None)
    environment["PYTHONPATH"] = str(STACK)
    environment["AINATIVE_STACK_SOURCE"] = str(STACK)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["GIT_CEILING_DIRECTORIES"] = str(project.parent)
    if git and not (project / ".git").exists():
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.email",
                        "setup@example.com"], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.name",
                        "Setup Test"], check=True)
    return subprocess.run(
        [sys.executable, "-m", "ainative.cli", "setup",
         "--project", str(project), "--home", str(home), *args],
        capture_output=True, text=True, errors="replace", env=environment,
        stdin=subprocess.DEVNULL, cwd=str(project.parent))


class SetupWizard(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="setup-wizard-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()

    def test_without_a_terminal_and_without_choices_it_refuses(self):
        completed = _run(self.project, self.home)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("SETUP_CHOICES_REQUIRED", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertFalse((self.project / ".ai-native").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_non_interactive_standard_installs_project_and_machine(self):
        completed = _run(self.project, self.home, "--non-interactive",
                         "--profile", "standard", "--machine")
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
        self.assertTrue((self.project / ".ai-native" / "lifecycle" / "state.json").is_file())
        self.assertTrue((self.home / ".ai-native" / "machine.json").is_file())
        self.assertIn("Doctor: healthy", completed.stdout)
        state = json.loads((self.project / ".ai-native" / "lifecycle" / "state.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(state["active_profile"], "standard")

    def test_without_the_machine_flag_the_home_is_untouched(self):
        completed = _run(self.project, self.home, "--non-interactive",
                         "--profile", "standard")
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
        self.assertTrue((self.project / ".ai-native" / "lifecycle" / "state.json").is_file())
        self.assertFalse((self.home / ".ai-native" / "machine.json").exists())

    def test_json_mode_is_parseable_and_the_prompts_never_run(self):
        completed = _run(self.project, self.home, "--json",
                         "--profile", "standard", "--machine")
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
        record = json.loads(completed.stdout)
        self.assertEqual(record["operation"], "setup")
        self.assertEqual(record["profile"], "standard")
        self.assertTrue(record["doctor"]["healthy"])
        self.assertIsNotNone(record["machine_install"])

    def test_dry_run_writes_nothing(self):
        completed = _run(self.project, self.home, "--non-interactive",
                         "--profile", "standard", "--machine", "--dry-run")
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
        self.assertFalse((self.project / ".ai-native" / "lifecycle" / "state.json").exists())
        self.assertFalse((self.home / ".ai-native" / "machine.json").exists())

    def test_verified_needs_git_and_refuses_cleanly_without_it(self):
        shutil.rmtree(self.project / ".git", ignore_errors=True)
        completed = _run(self.project, self.home, "--non-interactive",
                         "--profile", "verified", "--machine", git=False)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("GIT_REPOSITORY_REQUIRED", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertFalse((self.home / ".ai-native" / "machine.json").exists())


if __name__ == "__main__":
    unittest.main()
