"""Maintenance: compose owners, dry-run by default, never touch audit/canonical."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import continuity as continuitylib
from ainative.knowledge import imports as importslib
from ainative.knowledge import maintenance as maintenancelib


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    (project / "notes.md").write_text("canonical text\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _working_dir(project: Path) -> Path:
    return project / ".ai-native" / "state" / "knowledge" / "working"


class MaintenanceTests(unittest.TestCase):
    def test_maintain_dry_run_reports_and_removes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            continuitylib.checkpoint(project, {"task": "t"}, ttl_seconds=-1)
            before = sorted(_working_dir(project).glob("ckpt_*.json"))
            report = maintenancelib.maintain(project)
            self.assertFalse(report["apply_safe"])
            self.assertGreaterEqual(report["removable_expired_checkpoints"], 1)
            after = sorted(_working_dir(project).glob("ckpt_*.json"))
            self.assertEqual(before, after)

    def test_apply_safe_prunes_only_expired_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            expired = continuitylib.checkpoint(project, {"task": "old"}, ttl_seconds=-1)
            valid = continuitylib.checkpoint(project, {"task": "current"}, ttl_seconds=3600)
            report = maintenancelib.maintain(project, apply_safe=True)
            self.assertEqual("applied-safe", report["action"])
            self.assertTrue(any(expired["checkpoint_id"] in name for name in report["removed"]))
            remaining = sorted(path.name for path in _working_dir(project).glob("ckpt_*.json"))
            self.assertEqual([f"{valid['checkpoint_id']}.json"], remaining)

    def test_maintain_never_touches_candidate_store_or_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "maintainsandbox"
            source = root / "export.json"
            source.write_text(json.dumps([{"claim": "workflow review happens on Fridays",
                                           "identity_key": f"project/{slug}/workflow/review"}]),
                              encoding="utf-8")
            importslib.apply(project, source, harness="claude", project_slug=slug)
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            audit_dir = project / ".ai-native" / "audit" / "knowledge"
            before_candidates = candidates.read_bytes()
            before_audit = sorted(path.name for path in audit_dir.glob("*"))
            continuitylib.checkpoint(project, {"task": "t"}, ttl_seconds=-1)
            maintenancelib.maintain(project, apply_safe=True)
            self.assertEqual(before_candidates, candidates.read_bytes())
            self.assertEqual(before_audit, sorted(path.name for path in audit_dir.glob("*")))

    def test_export_copies_stores_with_manifest_digests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "exportsandbox"
            source = root / "export.json"
            source.write_text(json.dumps([{"claim": "workflow review happens on Fridays",
                                           "identity_key": f"project/{slug}/workflow/review"}]),
                              encoding="utf-8")
            importslib.apply(project, source, harness="codex", project_slug=slug)
            target = root / "bundle"
            report = maintenancelib.export(project, target)
            self.assertGreaterEqual(report["exported"], 1)
            manifest = json.loads((target / "MANIFEST.json").read_text(encoding="utf-8"))
            for entry in manifest["entries"]:
                payload = (target / entry["exported"]).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])

    def test_reset_derived_empty_registry_is_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            report = maintenancelib.reset_derived(project, apply_safe=True)
            self.assertEqual([], report["registered"])
            self.assertEqual([], report["removed"])


if __name__ == "__main__":
    unittest.main()
