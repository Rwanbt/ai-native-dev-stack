import tempfile
import unittest
from pathlib import Path

from ainative.multivault.confinement import ResultConfinement


def allow(_path: str) -> bool:
    return True


def deny(_path: str) -> bool:
    return False


class ResultConfinementTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name)
        self.repository = str(root / "repo-a")
        self.other = str(root / "repo-b")

    def tearDown(self):
        self._temporary.cleanup()

    def test_result_outside_envelope_is_denied(self):
        gate = ResultConfinement("project-a", (self.repository,), allow)
        self.assertEqual("DENY", gate.admit(str(Path(self.other) / "file.md"), "project-a").decision)

    def test_cross_project_result_is_denied_even_inside_envelope(self):
        gate = ResultConfinement("project-a", (self.repository,), allow)
        self.assertEqual("DENY", gate.admit(str(Path(self.repository) / "file.md"), "project-b").decision)

    def test_vault_protocol_denial_is_denied(self):
        gate = ResultConfinement("project-a", (self.repository,), deny)
        self.assertEqual("DENY", gate.admit(str(Path(self.repository) / "file.md"), "project-a").decision)

    def test_relative_path_is_denied(self):
        gate = ResultConfinement("project-a", (self.repository,), allow)
        self.assertEqual("DENY", gate.admit("repo-a/file.md", "project-a").decision)

    def test_root_and_nested_paths_are_allowed(self):
        gate = ResultConfinement("project-a", (self.repository,), allow)
        self.assertEqual("ALLOW", gate.admit(self.repository, "project-a").decision)
        self.assertEqual("ALLOW", gate.admit(str(Path(self.repository) / "notes" / "file.md"), "project-a").decision)

    def test_parent_traversal_cannot_escape_the_envelope(self):
        gate = ResultConfinement("project-a", (self.repository,), allow)
        escaping = str(Path(self.repository) / ".." / "repo-b" / "file.md")
        self.assertEqual("DENY", gate.admit(escaping, "project-a").decision)