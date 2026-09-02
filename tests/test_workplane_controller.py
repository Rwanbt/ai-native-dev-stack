import json
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.controller import ControllerError, WorkController


class WorkControllerTests(unittest.TestCase):
    def test_create_mutate_and_detect_direct_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            first = controller.create({"requirements": {"value": "initial"}})
            self.assertEqual(1, first["revision"])
            self.assertEqual(1, controller.read()["revision"])
            second = controller.mutate(1, {"requirements": {"value": "next"}})
            self.assertEqual(2, second["revision"])
            with self.assertRaisesRegex(ControllerError, "STALE_REVISION"):
                controller.mutate(1, {"requirements": {"value": "stale"}})
            pointer = second["artifacts"]["requirements"]
            path = Path(directory) / pointer["path"]
            path.write_text('{"value":"tampered"}', encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "UNEXPECTED_MUTATION"):
                controller.read()

    def test_manifest_is_last_commit_marker_and_staging_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            controller.create({"tasks": {"done": False}})
            self.assertTrue((Path(directory) / "manifest.json").is_file())
            self.assertEqual(0, controller.recover_staging())
            with self.assertRaisesRegex(ControllerError, "WORK_ALREADY_EXISTS"):
                controller.create({"tasks": {"done": True}})

    def test_concurrent_writer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            controller.root.mkdir(parents=True, exist_ok=True)
            (controller.root / ".controller.lock").write_text("held", encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "CONCURRENT_WRITER"):
                controller.create({"tasks": {"done": False}})

    def test_crash_before_manifest_preserves_previous_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            WorkController(directory).create({"tasks": {"revision": 1}})
            def crash(step):
                if step == "after_promotion_before_manifest":
                    raise RuntimeError("injected crash")
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                WorkController(directory, failure_injector=crash).mutate(1, {"tasks": {"revision": 2}})
            self.assertEqual(1, WorkController(directory).read()["revision"])
            recovered = WorkController(directory).recover_staging()
            self.assertEqual(1, recovered)
            self.assertFalse((Path(directory) / "revisions" / "2").exists())

    def test_recovery_discards_orphan_revision_before_first_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            orphan = root / "revisions" / "1"
            orphan.mkdir(parents=True)
            (orphan / "tasks.json").write_text('{"orphan":true}', encoding="utf-8")
            manifest = WorkController(directory).create({"tasks": {"fresh": True}})
            self.assertEqual(1, manifest["revision"])
            self.assertEqual({"fresh": True}, json.loads((root / "revisions" / "1" / "tasks.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
