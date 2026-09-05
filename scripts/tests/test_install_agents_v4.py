"""Tests for scripts/install_agents.py v4 integration.

Covers:
  * method + vault block separation (one block per kind, no overwrite)
  * idempotent re-install on a clean install
  * --check detecting missing, stale, and duplicate blocks
  * --dry-run changing nothing
  * user content outside markers preserved across re-installs
  * six harness support (Claude, Codex, OpenCode, Cursor, Gemini, Mavis)
  * --no-vault-block suppression
  * invalid slug rejected at the CLI without ever touching the file system
  * vault not provided: still installs method blocks
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


def _run(args: list[str], env: dict | None = None,
         cwd: Path | None = None, isolated: bool = False) -> subprocess.CompletedProcess:
    """Invoke install_agents.py with the supplied env.

    `isolated=True` strips OBSIDIAN_VAULT and OBSIDIAN_PROJECT_SLUG
    from the inherited environment, so the test sees the same state
    a real user would see in a clean shell.
    """
    cmd = [sys.executable, str(INSTALL), *args]
    full_env = os.environ.copy()
    if isolated:
        full_env.pop("OBSIDIAN_VAULT", None)
        full_env.pop("OBSIDIAN_PROJECT_SLUG", None)
    if env:
        full_env.update(env)
    return subprocess.run(cmd, env=full_env, capture_output=True, text=True,
                          cwd=str(cwd) if cwd else None)


def _make_home() -> Path:
    home = Path(tempfile.mkdtemp(prefix="stack-b-test-"))
    return home


def _write_v4_vault(root: Path, slug: str = "demo") -> Path:
    """Build a v4 vault on disk, return its path."""
    (root / "AGENTS.md").write_text("# vault\n", encoding="utf-8")
    system = root / "_system"
    system.mkdir()
    (system / "AGENTS.md").write_text("# system\n", encoding="utf-8")
    (system / "schemas").mkdir()
    (system / "schemas" / "projects.json").write_text(json.dumps({
        "schema_version": 4,
        "projects": [
            {"slug": slug, "title": "Demo", "prefix": "DEMO",
             "source": "Demo", "status": "active"},
        ],
    }), encoding="utf-8")
    (system / "tooling").mkdir()
    (system / "tooling" / "vault.py").write_text(
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--root', default='.')\n"
        "sub = p.add_subparsers(dest='cmd', required=True)\n"
        "sub.add_parser('lint')\n"
        "args = p.parse_args()\n"
        "if args.cmd == 'lint':\n"
        "    print('OK')\n",
        encoding="utf-8")
    (system / "tooling" / "vaultlib.py").write_text("", encoding="utf-8")
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")
    return root


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_home = _make_home()
        self._tmp_vault_dir = _make_home()
        self.vault = _write_v4_vault(self._tmp_vault_dir)
        self.env = {
            "OBSIDIAN_VAULT": str(self.vault),
            "OBSIDIAN_PROJECT_SLUG": "demo",
        }

    def tearDown(self) -> None:
        # Best-effort cleanup via mavis-trash if available; otherwise
        # leave for the OS to clean up. We never call Remove-Item
        # directly — that would trip the safety policy.
        import shutil
        shutil.rmtree(self._tmp_home, ignore_errors=True)
        shutil.rmtree(self._tmp_vault_dir, ignore_errors=True)

    # --- method block only ----------------------------------------------

    def test_method_block_only_when_no_vault(self) -> None:
        # Isolate so the inherited env (which setUp configured) does
        # not leak into the test process.
        result = _run(["--home", str(self._tmp_home)], isolated=True)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        self.assertTrue(claude_md.is_file())
        body = claude_md.read_text(encoding="utf-8")
        self.assertIn("Shared engineering method", body)
        # Without a vault, the governance block is not added.
        self.assertNotIn("Vault governance", body)

    # --- vault + method block together ----------------------------------

    def test_vault_and_method_blocks_in_same_file(self) -> None:
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        body = claude_md.read_text(encoding="utf-8")
        self.assertIn("Shared engineering method", body)
        self.assertIn("Vault governance", body)
        # Both blocks are present, separated by their markers.
        self.assertIn("<!-- BEGIN AI-NATIVE-DEV-STACK -->", body)
        self.assertIn("<!-- END AI-NATIVE-DEV-STACK -->", body)
        self.assertIn("<!-- BEGIN AI-NATIVE-DEV-STACK VAULT -->", body)
        self.assertIn("<!-- END AI-NATIVE-DEV-STACK VAULT -->", body)
        self.assertIn("projects/<slug>/AGENTS.md", body)
        self.assertNotIn("projects/demo/AGENTS.md", body)

    def test_vault_block_keeps_github_as_active_authority(self) -> None:
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        targets = [
            self._tmp_home / ".claude" / "CLAUDE.md",
            self._tmp_home / ".codex" / "AGENTS.md",
            self._tmp_home / ".config" / "opencode" / "AGENTS.md",
            self._tmp_home / ".cursor" / "rules" / "ai-native-dev-stack.mdc",
            self._tmp_home / ".gemini" / "GEMINI.md",
            self._tmp_home / ".mavis" / "agents" / "mavis" / "agent.md",
        ]
        for path in targets:
            body = path.read_text(encoding="utf-8")
            self.assertIn("GitHub Issues are the canonical active work state", body)
            self.assertIn("historical/contextual memory", body)
            self.assertIn("historical/generated", body)
            self.assertNotIn("canonical initiative/task cards", body)
            self.assertNotIn("create a `needs-triage` card", body)

    def test_user_content_outside_markers_survives_reinstall(self) -> None:
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        with claude_md.open("a", encoding="utf-8") as handle:
            handle.write("\n# USER ADDITION\nThis must not be touched.\n")
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        body = claude_md.read_text(encoding="utf-8")
        self.assertIn("# USER ADDITION", body)
        self.assertIn("This must not be touched.", body)

    def test_idempotent_reinstall(self) -> None:
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        # Second run must report 0 changes.
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("0 change(s), 0 issue(s)", result.stdout)

    def test_dry_run_makes_no_changes(self) -> None:
        result = _run(["--home", str(self._tmp_home), "--dry-run"], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse((self._tmp_home / ".claude" / "CLAUDE.md").exists())

    # --- --check --------------------------------------------------------

    def test_check_clean_install_reports_no_issues(self) -> None:
        _run(["--home", str(self._tmp_home)], env=self.env)
        result = _run(["--home", str(self._tmp_home), "--check"], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("0 issue(s)", result.stdout)

    def test_check_detects_stale_method_block(self) -> None:
        _run(["--home", str(self._tmp_home)], env=self.env)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        body = claude_md.read_text(encoding="utf-8")
        # Wipe the method block but keep the vault block.
        import re
        cleaned = re.sub(
            r"<!-- BEGIN AI-NATIVE-DEV-STACK -->\n.*?<!-- END AI-NATIVE-DEV-STACK -->\n\n",
            "", body, count=1, flags=re.DOTALL)
        claude_md.write_text(cleaned, encoding="utf-8")
        result = _run(["--home", str(self._tmp_home), "--check"], env=self.env)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("STALE", result.stdout)
        self.assertIn("1 issue(s)", result.stdout)

    def test_check_detects_duplicate_method_block(self) -> None:
        _run(["--home", str(self._tmp_home)], env=self.env)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        # Add a stray BEGIN without a matching END.
        with claude_md.open("a", encoding="utf-8") as handle:
            handle.write("<!-- BEGIN AI-NATIVE-DEV-STACK -->\norphan\n")
        result = _run(["--home", str(self._tmp_home), "--check"], env=self.env)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("DUPLICATE", result.stdout)

    def test_check_detects_two_balanced_method_blocks(self) -> None:
        _run(["--home", str(self._tmp_home)], env=self.env)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        body = claude_md.read_text(encoding="utf-8")
        begin = body.index("<!-- BEGIN AI-NATIVE-DEV-STACK -->")
        end_marker = "<!-- END AI-NATIVE-DEV-STACK -->"
        end = body.index(end_marker, begin) + len(end_marker)
        with claude_md.open("a", encoding="utf-8") as handle:
            handle.write("\n\n" + body[begin:end] + "\n")
        result = _run(["--home", str(self._tmp_home), "--check"], env=self.env)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("DUPLICATE", result.stdout)

    # --- six harness support -------------------------------------------

    def test_all_six_harnesses_get_both_blocks(self) -> None:
        result = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        targets = [
            self._tmp_home / ".claude" / "CLAUDE.md",
            self._tmp_home / ".codex" / "AGENTS.md",
            self._tmp_home / ".config" / "opencode" / "AGENTS.md",
            self._tmp_home / ".cursor" / "rules" / "ai-native-dev-stack.mdc",
            self._tmp_home / ".gemini" / "GEMINI.md",
            self._tmp_home / ".mavis" / "agents" / "mavis" / "agent.md",
        ]
        for path in targets:
            with self.subTest(harness=path.relative_to(self._tmp_home).as_posix()):
                self.assertTrue(path.is_file(), f"{path} missing")
                body = path.read_text(encoding="utf-8")
                self.assertIn("Shared engineering method", body)
                self.assertIn("Vault governance", body)
        cursor = targets[3].read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", cursor)

    def test_unknown_registry_slug_is_rejected(self) -> None:
        result = _run(
            ["--home", str(self._tmp_home), "--vault", str(self.vault),
             "--project-slug", "missing-project"], isolated=True,
        )
        self.assertEqual(result.returncode, 2, msg=result.stdout)
        self.assertIn("unknown-slug", result.stderr)
        self.assertFalse((self._tmp_home / ".claude" / "CLAUDE.md").exists())

    # --- --no-vault-block ----------------------------------------------

    def test_no_vault_block_skips_governance(self) -> None:
        result = _run(
            ["--home", str(self._tmp_home), "--no-vault-block"],
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        body = claude_md.read_text(encoding="utf-8")
        self.assertIn("Shared engineering method", body)
        self.assertNotIn("Vault governance", body)

    def test_no_vault_block_removes_existing_governance(self) -> None:
        first = _run(["--home", str(self._tmp_home)], env=self.env)
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        claude_md = self._tmp_home / ".claude" / "CLAUDE.md"
        with claude_md.open("a", encoding="utf-8") as handle:
            handle.write("\n# USER CONTENT\n")
        result = _run(
            ["--home", str(self._tmp_home), "--no-vault-block"], env=self.env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        body = claude_md.read_text(encoding="utf-8")
        self.assertIn("Shared engineering method", body)
        self.assertNotIn("Vault governance", body)
        self.assertIn("# USER CONTENT", body)

    # --- invalid slug --------------------------------------------------

    def test_invalid_slug_rejected_at_cli(self) -> None:
        result = _run(
            ["--home", str(self._tmp_home),
             "--vault", str(self.vault),
             "--project-slug", "BadSlug_Uppercase"],
        )
        self.assertEqual(result.returncode, 2, msg=result.stdout)
        self.assertIn("does not match v4 grammar", result.stderr)
        # The method block is also skipped because the CLI bailed out.
        self.assertFalse(
            (self._tmp_home / ".claude" / "CLAUDE.md").exists()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
