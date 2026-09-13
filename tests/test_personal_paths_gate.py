"""The machine-path gate must actually block, and its allowlist must be earned.

Two failure modes matter more than the happy path: a gate that cannot fail
(mutation proof, first test) and a gate that fails on legitimate documentation
(the allowed-line cases). The allowlist entries exist because rewriting
historical evidence would change the record, not because the pattern is fine.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "check_personal_paths", REPO / "scripts" / "check_personal_paths.py")
gate = importlib.util.module_from_spec(_spec)
sys.modules["check_personal_paths"] = gate
_spec.loader.exec_module(gate)


class GateOnTheCheckout(unittest.TestCase):

    def test_the_shipped_tree_has_no_machine_paths(self):
        self.assertEqual(gate.scan(REPO), [])


class GateMutation(unittest.TestCase):
    """The property is that an injected machine path fails the gate."""

    def run_gate_on(self, content: str) -> list[dict]:
        with tempfile.TemporaryDirectory(prefix="path-gate-") as staging:
            root = Path(staging)
            (root / "module.py").write_text(content, encoding="utf-8")
            return gate.scan(root, files=["module.py"])

    def test_a_windows_profile_path_is_refused(self):
        hits = self.run_gate_on('HOME = r"C:\\Users\\example\\project"\n')
        self.assertTrue(hits, "an injected Windows profile path passed the gate")
        self.assertEqual(hits[0]["pattern"], "windows-profile")

    def test_a_posix_home_path_is_refused(self):
        hits = self.run_gate_on('root = "/home/example/project"\n')
        self.assertTrue(hits, "an injected Linux home path passed the gate")

    def test_a_documents_directory_is_refused(self):
        hits = self.run_gate_on('vault = "D:\\\\Documents\\\\Obsidian"\n')
        self.assertTrue(hits)

    def test_the_local_account_in_a_path_is_refused(self):
        hits = self.run_gate_on('p = "/home/barat/project"\n')
        self.assertTrue(hits)

    def test_a_deliberate_documentation_example_is_allowed(self):
        # The real README sentence that documents the absence of a hard-coded
        # path; using the shipped line keeps this test honest about escaping.
        line = next(item for item in
                    (REPO / "README.md").read_text(encoding="utf-8").splitlines()
                    if "There is no" in item and "Documents" in item)
        with tempfile.TemporaryDirectory(prefix="path-gate-") as staging:
            root = Path(staging)
            (root / "README.md").write_text(line + "\n", encoding="utf-8")
            hits = gate.scan(root, files=["README.md"])
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()