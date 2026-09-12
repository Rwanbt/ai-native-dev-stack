"""Knowledge isolation E2E: zero leakage across projects, ambient env and gates.

Phase 13 of the convergence program, at the level the current architecture
actually governs: knowledge stores are project-confined, identity enforces the
target project, staleness refuses out-of-project refs, mutation-gated states
refuse without a verified authority, and no ambient environment variable or
current working directory can redirect a governed write.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import errors as errorslib
from ainative.knowledge import imports as importslib
from ainative.knowledge import staleness as stalenesslib
from ainative.knowledge import states as stateslib
from ainative.knowledge import store as storelib

REPO_ROOT = str(Path(__file__).resolve().parents[1])

CAPTURE_IN_SUBPROCESS = (
    "import sys, json; sys.path.insert(0, sys.argv[1]); "
    "from pathlib import Path; from ainative.knowledge import imports; "
    "report = imports.apply(Path(sys.argv[2]), Path(sys.argv[3]), harness='claude', "
    "project_slug=sys.argv[4]); print(json.dumps(report))")


def _repo(directory: str, name: str = "") -> Path:
    project = Path(directory) / name if name else Path(directory)
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


class KnowledgeIsolationTests(unittest.TestCase):
    def test_cross_project_import_is_refused_with_zero_writes_on_both_sides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory, "project-a")
            other = _repo(directory, "project-b")
            source = root / "items.json"
            source.write_text(json.dumps([{"claim": "rule from b",
                                           "identity_key": "project/project-b/context/session"}]),
                              encoding="utf-8")
            report = importslib.apply(project, source, harness="claude",
                                      project_slug="project-a")
            self.assertEqual([], report["created"])
            self.assertTrue(any("KNOWLEDGE_IDENTITY_KEY_INVALID" in item["reason"]
                                for item in report["refused"]))
            self.assertEqual([], storelib.list_candidates(project))
            self.assertFalse((other / ".ai-native").exists())

    def test_ambient_environment_and_cwd_never_redirect_the_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory, "project-a")
            neutral_cwd = root / "neutral-cwd"
            neutral_cwd.mkdir()
            source = root / "items.json"
            source.write_text(json.dumps([{"claim": "workflow review happens on Fridays",
                                           "identity_key": "project/project-a/workflow/review"}]),
                              encoding="utf-8")
            environment = dict(os.environ)
            environment.update({"OBSIDIAN_API_KEY": "ambient-should-be-ignored",
                                "OBSIDIAN_VAULT": str(root / "ghost-vault"),
                                "AI_NATIVE_VAULT": str(root / "ghost-vault")})
            completed = subprocess.run(
                [sys.executable, "-c", CAPTURE_IN_SUBPROCESS, REPO_ROOT,
                 str(project), str(source), "project-a"],
                cwd=str(neutral_cwd), env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(1, len(report["created"]))
            self.assertTrue((project / ".ai-native").is_dir())
            self.assertFalse((neutral_cwd / ".ai-native").exists())
            self.assertFalse((root / "ghost-vault").exists())

    def test_mutation_gated_states_refuse_without_a_verified_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory, "project-a")
            source = root / "items.json"
            source.write_text(json.dumps([{"claim": "workflow review happens on Fridays",
                                           "identity_key": "project/project-a/workflow/review"}]),
                              encoding="utf-8")
            applied = importslib.apply(project, source, harness="claude", project_slug="project-a")
            candidate_id = applied["created"][0]
            for current in sorted(stateslib.STATES):
                try:
                    result = stateslib.transition(current, stateslib.APPROVED)
                except errorslib.KnowledgeError as error:
                    self.assertIn(error.code,
                                  ("KNOWLEDGE_GATE_CLOSED",
                                   "KNOWLEDGE_ILLEGAL_STATE_TRANSITION"))
                    continue
                self.fail(f"no authority path may approve knowledge: {current} -> "
                          f"{result} without a verified authority")

    def test_dependency_outside_the_project_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory, "project-a")
            result = stalenesslib.evaluate(project, [
                {"kind": "source_path", "ref": "../project-b/secret.txt", "digest": "x"}])
            self.assertEqual(1, len(result["refused"]))
            self.assertEqual(stalenesslib.DEPENDENCY_REFUSED, result["refused"][0]["code"])
            self.assertEqual(stalenesslib.UNKNOWN, result["signal"])


if __name__ == "__main__":
    unittest.main()
