import os
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.snapshot import SnapshotError, snapshot_files


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
