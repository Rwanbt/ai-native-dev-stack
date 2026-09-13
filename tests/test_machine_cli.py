"""`ainative machine` — the product surface over the ownership manifest.

Each test drives the installed CLI as a user would, against a throwaway home:
init records what it wrote, status reports each asset, doctor renders a
verdict, repair re-creates only what the manifest proves, uninstall removes
only what it recorded. A corrupt manifest fails closed; an absent manifest is
not an error.
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


def _run(home: Path, *args: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    for name in ("OBSIDIAN_VAULT", "OBSIDIAN_PROJECT_SLUG"):
        environment.pop(name, None)
    environment["PYTHONPATH"] = str(STACK)
    environment["AINATIVE_STACK_SOURCE"] = str(STACK)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["GIT_CEILING_DIRECTORIES"] = str(home.parent)
    return subprocess.run(
        [sys.executable, "-m", "ainative.cli", *args, "--home", str(home)],
        capture_output=True, text=True, errors="replace", env=environment,
        cwd=str(home.parent))


class MachineCli(unittest.TestCase):

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="machine-cli-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        self.home.mkdir()
        completed = _run(self.home, "machine", "init")
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)

    def manifest(self) -> dict:
        return json.loads((self.home / ".ai-native" / "machine.json")
                          .read_text(encoding="utf-8"))

    def asset(self, kind: str) -> dict:
        return next(item for item in self.manifest()["assets"]
                    if item["kind"] == kind)

    def test_init_records_a_manifest_with_all_three_asset_kinds(self):
        record = self.manifest()
        kinds = {asset["kind"] for asset in record["assets"]}
        self.assertEqual(kinds, {"link", "block", "rendered"})
        self.assertEqual(record["schema_version"], 2)
        self.assertTrue(record.get("stack_root"))
        block = self.asset("block")
        self.assertTrue(block.get("heading") or block.get("vault"))
        rendered = self.asset("rendered")
        self.assertIn("digest", rendered)
        self.assertIn("template", rendered)
        for asset in record["assets"]:
            self.assertIsInstance(asset.get("existed_before"), bool, asset)

    def test_existed_before_distinguishes_user_files_from_fresh_ones(self):
        root = Path(tempfile.mkdtemp(prefix="machine-cli-preexisting-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        home = root / "home"
        (home / ".claude").mkdir(parents=True)
        user = "# user rules, written by hand\n"
        (home / ".claude" / "CLAUDE.md").write_text(user, encoding="utf-8")
        completed = _run(home, "machine", "init")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        record = json.loads((home / ".ai-native" / "machine.json")
                            .read_text(encoding="utf-8"))
        by_path = {asset["path"]: asset for asset in record["assets"]}
        self.assertTrue(by_path[".claude/CLAUDE.md"]["existed_before"],
                        "a hand-written file existed before the install")
        self.assertFalse(by_path[".gemini/GEMINI.md"]["existed_before"],
                         "a file this install created did not exist before")
        self.assertIn(user, (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8"))

        # A re-run must not rewrite history: the answers survive.
        rerun = _run(home, "machine", "init")
        self.assertEqual(rerun.returncode, 0, rerun.stdout)
        record = json.loads((home / ".ai-native" / "machine.json")
                            .read_text(encoding="utf-8"))
        by_path = {asset["path"]: asset for asset in record["assets"]}
        self.assertTrue(by_path[".claude/CLAUDE.md"]["existed_before"])
        self.assertFalse(by_path[".gemini/GEMINI.md"]["existed_before"])

    def test_dry_run_json_projects_the_record_without_writing(self):
        root = Path(tempfile.mkdtemp(prefix="machine-cli-dryjson-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        home = root / "home"
        home.mkdir()
        completed = _run(home, "machine", "init", "--dry-run", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["manifest"], None)
        self.assertGreater(len(report["recorded"]), 20)
        self.assertTrue(all(isinstance(asset.get("existed_before"), bool)
                            for asset in report["recorded"]))
        self.assertFalse((home / ".ai-native" / "machine.json").exists())

    def test_init_dry_run_writes_nothing(self):
        root = Path(tempfile.mkdtemp(prefix="machine-cli-dry-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        home = root / "home"
        home.mkdir()
        completed = _run(home, "machine", "init", "--dry-run")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse((home / ".ai-native" / "machine.json").exists())
        self.assertEqual(list(home.iterdir()), [])

    def test_status_reports_every_asset_ok(self):
        completed = _run(self.home, "machine", "status", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["healthy"])
        self.assertEqual(report["counts"], {"OK": len(report["assets"])})
        self.assertGreaterEqual(len(report["assets"]), 20)

    def test_status_without_a_manifest_is_not_an_error(self):
        root = Path(tempfile.mkdtemp(prefix="machine-cli-none-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        home = root / "home"
        home.mkdir()
        completed = _run(home, "machine", "status")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no machine manifest", completed.stdout)

    def test_doctor_fails_after_a_recorded_asset_is_deleted(self):
        link = self.asset("link")
        (self.home / link["path"]).unlink()
        completed = _run(self.home, "machine", "doctor")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("MISSING", completed.stdout)

    def test_repair_recreates_only_what_the_manifest_proves(self):
        link = self.asset("link")
        (self.home / link["path"]).unlink()
        completed = _run(self.home, "machine", "repair")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("repaired:     1", completed.stdout)
        self.assertTrue((self.home / link["path"]).exists())
        doctor = _run(self.home, "machine", "doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout)

    def test_repair_preserves_a_user_edited_rendered_file(self):
        rendered = self.asset("rendered")
        target = self.home / rendered["path"]
        target.write_text("// mine now\n", encoding="utf-8")
        completed = _run(self.home, "machine", "repair")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), "// mine now\n")
        self.assertIn("preserved:", completed.stdout)

    def test_repair_preserves_a_retargeted_link(self):
        link = self.asset("link")
        target = self.home / link["path"]
        target.unlink()
        target.mkdir()
        (target / "SKILL.md").write_text("# someone else's\n", encoding="utf-8")
        completed = _run(self.home, "machine", "repair")
        self.assertIn("preserved:", completed.stdout)
        self.assertTrue((target / "SKILL.md").is_file())
        doctor = _run(self.home, "machine", "doctor")
        self.assertEqual(doctor.returncode, 1)
        self.assertIn("DRIFTED", doctor.stdout)

    def test_uninstall_preserves_user_files_and_edited_renders(self):
        notes = self.home / ".claude" / "MY-NOTES.md"
        notes.write_text("# private\n", encoding="utf-8")
        rendered = self.asset("rendered")
        (self.home / rendered["path"]).write_text("// edited\n", encoding="utf-8")
        completed = _run(self.home, "machine", "uninstall")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(notes.is_file())
        edited = self.home / rendered["path"]
        self.assertTrue(edited.is_file())
        self.assertIn("PRESERVE", completed.stdout)
        self.assertFalse((self.home / ".ai-native" / "machine.json").exists())

    def test_uninstall_dry_run_changes_nothing(self):
        before = (self.home / ".claude" / "CLAUDE.md").read_bytes()
        completed = _run(self.home, "machine", "uninstall", "--dry-run")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((self.home / ".ai-native" / "machine.json").exists())
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_bytes(), before)

    def test_a_corrupt_manifest_fails_closed_with_no_writes(self):
        manifest = self.home / ".ai-native" / "machine.json"
        manifest.write_text("{not json", encoding="utf-8")
        before = (self.home / ".claude" / "CLAUDE.md").read_bytes()
        for command in ("init", "status", "doctor", "repair", "uninstall"):
            completed = _run(self.home, "machine", command)
            self.assertEqual(completed.returncode, 2, command)
            self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual((self.home / ".claude" / "CLAUDE.md").read_bytes(), before)
        self.assertEqual(manifest.read_text(encoding="utf-8"), "{not json")

    def test_a_schema_one_manifest_stays_readable(self):
        record = self.manifest()
        minimal = {"schema_version": 1, "installed_by": "scripts/install_agents.py",
                   "stack_version": "2.3.0", "assets": record["assets"]}
        for asset in minimal["assets"]:
            for field in ("heading", "template", "vault", "slug"):
                asset.pop(field, None)
        minimal.pop("stack_root", None)
        (self.home / ".ai-native" / "machine.json").write_text(
            json.dumps(minimal), encoding="utf-8")
        completed = _run(self.home, "machine", "status", "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["present"])
        self.assertEqual(report["schema_version"], 1)

    def test_vault_pair_and_slug_refusals_carry_stable_codes(self):
        vault = self.root / "vault"
        completed = _run(self.home, "machine", "init", "--vault", str(vault))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("MACHINE_VAULT_PAIR_REQUIRED", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

        completed = _run(self.home, "machine", "init", "--vault", str(vault),
                         "--project-slug", "Bad Slug")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("MACHINE_SLUG_INVALID", completed.stderr)

        (self.root / "not-a-vault").mkdir()
        completed = _run(self.home, "machine", "init",
                         "--vault", str(self.root / "not-a-vault"),
                         "--project-slug", "demo")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("MACHINE_VAULT_UNREADABLE", completed.stderr)


if __name__ == "__main__":
    unittest.main()
