"""The PostToolUse hook: configured by init, merged, preserved, diagnosed.

The central promise of the product — edit a source file, its AI_SUMMARY.md is
regenerated — used to require the user to hand-edit `.claude/settings.json`.
These tests pin the new contract end to end: `init` merges exactly one owned
entry into a file the user owns, a re-init never duplicates it, an uninstall and
a rollback remove only what is ours, an unparsable document is refused instead
of rewritten, and `doctor` fails when the automation it installed is missing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, read_text, write_text
from ainative.lifecycle import environment
from ainative.lifecycle import hooks as hookslib
from ainative.lifecycle import recovery
from ainative.lifecycle import transaction as txnlib
from ainative.lifecycle import updater as updaterlib
from ainative.lifecycle.errors import LifecycleError

USER_SETTINGS = {
    "model": "opus",
    "permissions": {"allow": ["Bash(ls:*)"]},
    "hooks": {
        "PreToolUse": [{"matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo user-pre"}]}],
        "PostToolUse": [{"matcher": "Read",
                         "hooks": [{"type": "command", "command": "echo user-post"}]}],
    },
}


def load_settings(project: Path) -> dict:
    return json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))


def owned_groups(settings: dict) -> list:
    from ainative.lifecycle.external_json import owns_group
    spec = hookslib.spec(Path("."))
    groups = settings.get("hooks", {}).get("PostToolUse", [])
    return [group for group in groups if owns_group(group, spec)]


class HookConfiguration(LifecycleTestCase):

    def test_init_configures_the_posttooluse_hook(self):
        self.install("standard")
        settings = load_settings(self.project)
        groups = owned_groups(settings)
        self.assertEqual(len(groups), 1, settings)
        command = groups[0]["hooks"][0]["command"]
        self.assertIn("tools/ai_docs/run_hook", command.replace("\\", "/"))
        wrapper = self.project / hookslib.wrapper_relative()
        self.assertTrue(wrapper.is_file(), wrapper)
        report = hookslib.hook_status(self.project)
        self.assertEqual(report["status"], hookslib.CONFIGURED, report)

    def test_a_user_settings_file_is_merged_not_replaced(self):
        write_text(self.project / ".claude" / "settings.json",
                   json.dumps(USER_SETTINGS, indent=2) + "\n")
        self.install("standard")
        settings = load_settings(self.project)
        self.assertEqual(settings["model"], "opus")
        self.assertEqual(settings["permissions"], USER_SETTINGS["permissions"])
        self.assertEqual(settings["hooks"]["PreToolUse"], USER_SETTINGS["hooks"]["PreToolUse"])
        command = json.dumps(settings["hooks"]["PostToolUse"])
        self.assertIn("echo user-post", command)
        self.assertEqual(len(owned_groups(settings)), 1, settings)

    def test_reinit_does_not_duplicate_the_hook(self):
        self.install("standard")
        before = read_text(self.project / ".claude" / "settings.json")
        self.install("standard")
        after = read_text(self.project / ".claude" / "settings.json")
        self.assertEqual(before, after)
        self.assertEqual(len(owned_groups(load_settings(self.project))), 1)

    def test_invalid_settings_json_is_refused_without_writing(self):
        broken = "{ not json at all"
        write_text(self.project / ".claude" / "settings.json", broken)
        result = self.install("standard")
        self.assertEqual(read_text(self.project / ".claude" / "settings.json"), broken)
        conflicts = [change for change in result.plan.changes
                     if change.action == "CONFLICT" and change.path == ".claude/settings.json"]
        self.assertTrue(conflicts, result.plan.changes)
        findings = [item for item in recovery.diagnose(self.project).findings
                    if item["component"] == "claude-hook"]
        self.assertEqual(findings[0]["status"], recovery.CORRUPTED, findings)

    def test_uninstall_removes_only_the_managed_entry(self):
        write_text(self.project / ".claude" / "settings.json",
                   json.dumps(USER_SETTINGS, indent=2) + "\n")
        self.install("standard")
        self.uninstall()
        settings = load_settings(self.project)
        self.assertIn("echo user-post", json.dumps(settings["hooks"]["PostToolUse"]))
        self.assertEqual(owned_groups(settings), [])

    def test_uninstall_deletes_a_settings_file_we_created_alone(self):
        self.install("standard")
        self.assertTrue((self.project / ".claude" / "settings.json").is_file())
        self.uninstall()
        self.assertFalse((self.project / ".claude" / "settings.json").exists())

    def test_a_rewritten_hook_entry_is_preserved(self):
        self.install("standard")
        settings = load_settings(self.project)
        for group in settings["hooks"]["PostToolUse"]:
            for entry in group.get("hooks", []):
                if "tools/ai_docs/run_hook" in entry.get("command", ""):
                    entry["command"] = "echo my own workflow"
        write_text(self.project / ".claude" / "settings.json",
                   json.dumps(settings, indent=2) + "\n")
        self.uninstall()
        self.assertIn("echo my own workflow",
                      read_text(self.project / ".claude" / "settings.json"))

    def test_rollback_removes_a_hook_file_the_install_created(self):
        self.install("standard")
        journals = [item for item in txnlib.read_journals(self.project)
                    if item.operation == "init" and item.state == txnlib.COMMITTED]
        self.assertTrue(journals)
        txnlib.undo(self.project, max(journals, key=lambda item: item.started_at))
        self.assertFalse((self.project / ".claude" / "settings.json").exists())

    def test_the_installed_wrapper_regenerates_a_summary(self):
        self.install("standard")
        # The fixture distribution ships stub tooling; the wrapper contract is
        # what this test exercises, so the real generator is copied in. The
        # generator itself is covered by the ai_docs suite.
        import shutil as _shutil

        from tests.lifecycle_support import REPO as _REPO
        for name in ("run_hook.sh", "run_hook.ps1", "update_on_edit.py",
                     "generate_ai_summary.py", "module_discovery.py",
                     "source_config.py"):
            _shutil.copy2(_REPO / "tools" / "ai_docs" / name,
                          self.project / "tools" / "ai_docs" / name)
        module = self.project / "src" / "demo"
        write_text(module / "AI_CONTEXT.md", "# Demo\nPurpose: test.\n")
        write_text(module / "code.py", "def hello():\n    return 1\n")
        payload = json.dumps({"tool_name": "Edit",
                              "tool_input": {"file_path": str(module / "code.py")}})
        wrapper = self.project / hookslib.wrapper_relative()
        if os.name == "nt":
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(wrapper)],
                input=payload, capture_output=True, text=True, timeout=180)
        else:
            completed = subprocess.run(["bash", str(wrapper)], input=payload,
                                       capture_output=True, text=True, timeout=180)
        diagnostic = (f"rc={completed.returncode} "
                      f"stdout={completed.stdout[-600:]!r} "
                      f"stderr={completed.stderr[-600:]!r}")
        self.assertEqual(completed.returncode, 0, diagnostic)
        summary = module / "AI_SUMMARY.md"
        self.assertTrue(summary.is_file(), diagnostic)
        self.assertIn("AI_SUMMARY", read_text(summary))


class HookDiagnostics(LifecycleTestCase):

    def test_doctor_json_reports_the_hook_as_ok(self):
        completed = self.cli("init", "--profile", "standard")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        completed = self.cli("doctor", "--json")
        record = json.loads(completed.stdout)
        hook = next(item for item in record["environment"] if item["name"] == "claude_hook")
        self.assertEqual(hook["status"], environment.OK, hook)

    def test_doctor_fails_when_the_configured_entry_disappears(self):
        self.cli("init", "--profile", "standard")
        (self.project / ".claude" / "settings.json").unlink()
        completed = self.cli("doctor", "--json")
        self.assertEqual(completed.returncode, 1)
        record = json.loads(completed.stdout)
        hook = next(item for item in record["environment"] if item["name"] == "claude_hook")
        self.assertEqual(hook["status"], environment.FAIL, hook)

    def test_doctor_reports_a_stale_wrapper_as_version_mismatch(self):
        self.install("standard")
        settings = load_settings(self.project)
        for group in settings["hooks"]["PostToolUse"]:
            for entry in group.get("hooks", []):
                command = entry.get("command", "")
                if "tools/ai_docs/run_hook" in command:
                    entry["command"] = command.replace(
                        str(self.project).replace("\\", "/"),
                        "/somewhere/else")
        write_text(self.project / ".claude" / "settings.json",
                   json.dumps(settings, indent=2) + "\n")
        report = hookslib.hook_status(self.project)
        self.assertIn(report["status"],
                      (hookslib.TARGET_MISSING, hookslib.VERSION_MISMATCH), report)


class NonGitPolicy(LifecycleTestCase):

    def nogit_project(self) -> Path:
        # GIT_CEILING_DIRECTORIES stops Git from discovering a repository that
        # encloses the test temp directory (the developer's home can be one).
        self.set_env("GIT_CEILING_DIRECTORIES", str(self.root))
        other = self.root / "plain"
        (other / "src").mkdir(parents=True)
        write_text(other / "src" / "app.py", "print('hi')\n")
        return other

    def test_standard_installs_outside_git_with_a_notice(self):
        from ainative.lifecycle import installer as installerlib
        other = self.nogit_project()
        result = installerlib.install(other, "standard", distribution=self.distribution,
                                      source=self.source)
        self.assertTrue(result.applied)
        self.assertTrue(any("not inside a Git repository" in notice
                            for notice in result.notices), result.notices)
        report = environment.environment_checks(other, installed=True)
        git = next(check for check in report if check["name"] == "git_repository")
        self.assertEqual(git["status"], environment.DEGRADED, git)

    def test_verified_refuses_outside_git(self):
        from ainative.lifecycle import installer as installerlib
        other = self.nogit_project()
        with self.assertRaises(LifecycleError) as raised:
            installerlib.install(other, "verified", distribution=self.distribution,
                                 source=self.source)
        self.assertEqual(raised.exception.code, "GIT_REPOSITORY_REQUIRED")
        self.assertFalse((other / ".ai-native").exists(),
                         "a refused Verified install wrote to the project")


if __name__ == "__main__":
    unittest.main()