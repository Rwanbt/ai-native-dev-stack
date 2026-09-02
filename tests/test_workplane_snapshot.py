import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.contracts import generate_uid
from ainative_workplane.evidence import build_verification_evidence
from ainative_workplane.freshness import evaluate_checkout_freshness
from ainative_workplane.snapshot import SnapshotError, build_repository_snapshot, snapshot_files, snapshot_reference


class SnapshotTests(unittest.TestCase):
    def test_scoped_streaming_digest_and_nested_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "file.bin").write_bytes(bytes(range(8)))
            result = snapshot_files(root, ["nested\\file.bin"])
            self.assertEqual(["nested/file.bin"], list(result))
            self.assertEqual(64, len(result["nested/file.bin"]))

    def test_symlink_escape_and_case_collision_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / f"outside-{os.getpid()}"
            outside.write_text("secret", encoding="utf-8")
            try:
                link = root / "escape"
                try:
                    link.symlink_to(outside)
                except (OSError, NotImplementedError):
                    self.skipTest("symlink creation unavailable")
                with self.assertRaisesRegex(SnapshotError, "SECURITY_REJECTED"):
                    snapshot_files(root, ["escape"])
            finally:
                outside.unlink(missing_ok=True)
            with self.assertRaisesRegex(Exception, "CASE_COLLISION"):
                snapshot_files(root, ["Foo.ts", "foo.ts"])

    def test_special_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fifo"
            try:
                os.mkfifo(path)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("special file creation unavailable")
            with self.assertRaisesRegex(SnapshotError, "SECURITY_REJECTED"):
                snapshot_files(directory, ["fifo"])

    def test_repository_snapshot_changes_when_scoped_or_dependency_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("first", encoding="utf-8")
            (root / "requirements.lock").write_text("one", encoding="utf-8")
            for args in (["init"], ["config", "user.email", "test@example.invalid"], ["config", "user.name", "Work Plane Test"], ["add", "."], ["commit", "-m", "initial"]):
                subprocess.run(["git", "-C", directory, *args], check=True, capture_output=True)
            common = {"scope": ["src/app.py"], "dependency_paths": ["requirements.lock"], "command_registry_digest": "a" * 64, "policy_digest": "b" * 64, "uid": "snapshot_01M1HTTR8NDA0X9XY6075Z7AJ8"}
            first = build_repository_snapshot(directory, **common)
            reference = lambda prefix: {"uid": generate_uid(prefix), "digest": "c" * 64}
            evidence = build_verification_evidence(
                {
                    "work": reference("work"), "contract_revision": 1, "contract_digest": "c" * 64,
                    "verification_specification": reference("verify"), "command_registry_digest": "a" * 64,
                    "policy_digest": "b" * 64, "approval_root": reference("root"),
                    "repository_snapshot": snapshot_reference(first), "producer": "test", "producer_version": "1",
                    "evidence_provenance": "LOCAL_UNTRUSTED",
                },
                command="check", result="PASS", exit_code=0, stdout=b"ok", stderr=b"", duration_ms=1, substance_metadata={},
            )
            (root / "src" / "app.py").write_text("second", encoding="utf-8")
            changed_scope = build_repository_snapshot(directory, **common)
            self.assertNotEqual(snapshot_reference(first)["digest"], snapshot_reference(changed_scope)["digest"])
            freshness = evaluate_checkout_freshness(
                evidence, repository_root=directory, scope=["src/app.py"], dependency_paths=["requirements.lock"],
                current_contract_digest="c" * 64, current_registry_digest="a" * 64, current_policy_digest="b" * 64,
                current_approval_root=evidence.artifact["approval_root"],
            )
            self.assertIn("STALE_SCOPE", freshness.states)
            (root / "requirements.lock").write_text("two", encoding="utf-8")
            changed_dependency = build_repository_snapshot(directory, **common)
            self.assertNotEqual(snapshot_reference(changed_scope)["digest"], snapshot_reference(changed_dependency)["digest"])
