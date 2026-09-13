"""Permissions: private state owner-only, managed docs readable (POSIX).

The stack used to write everything with whatever the umask produced, and the
Knowledge store's own control-path policy could not be exercised on a fresh
install because `.ai-native/state/` was not in the managed ignore region.

These tests run where POSIX mode bits exist. On Windows the mode is not the
mechanism (ACLs are a separate surface this project does not claim), so the
suite skips with that reason rather than asserting a translation.
"""

from __future__ import annotations

import os
import stat
import sys
import unittest

from tests.lifecycle_support import LifecycleTestCase, write_text
from ainative.lifecycle import state as statelib

POSIX_ONLY = unittest.skipIf(os.name == "nt",
                             "POSIX mode bits only; Windows ACLs are not claimed")


@POSIX_ONLY
class PrivateStatePermissions(LifecycleTestCase):

    def test_write_atomic_private_is_owner_only(self):
        target = self.root / "private.json"
        statelib.write_atomic_private(target, "{}\n")
        mode = stat.S_IMODE(target.stat().st_mode)
        self.assertEqual(mode, 0o600, oct(mode))

    def test_managed_documents_stay_readable(self):
        self.install("standard")
        agents = self.project / "AGENTS.md"
        mode = stat.S_IMODE(agents.stat().st_mode)
        self.assertTrue(mode & 0o044, f"managed doc not group/other readable: {oct(mode)}")

    def test_knowledge_state_is_owner_only_and_workable_after_init(self):
        self.install("standard")
        # The managed .gitignore region now carries .ai-native/state/, so a
        # capture works on a fresh install without any manual edit (#138).
        module = self.project / "notes.jsonl"
        completed = self.cli(
            "knowledge", "learn",
            "--claim", "A permission probe observation.",
            "--kind", "observation",
            "--identity-key", "project/project/cache/ttl")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        state_files = list((self.project / ".ai-native" / "state" / "knowledge").glob("*.jsonl"))
        self.assertTrue(state_files, "no knowledge state file was written")
        for path in state_files:
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600, f"{path.name}: {oct(mode)}")


if __name__ == "__main__":
    unittest.main()