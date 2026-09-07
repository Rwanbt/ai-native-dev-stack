"""PR3 gates: policy both directions, concurrency, crash, bounds, traversal."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ainative.knowledge import bounds as boundslib
from ainative.knowledge import paths as controlpaths
from ainative.knowledge import store as storelib
from ainative.knowledge.errors import KnowledgeError

GIT = shutil.which("git")
needs_git = unittest.skipUnless(GIT, "git executable required")


def _git(project: Path, *args: str) -> None:
    subprocess.run([GIT, "-C", str(project), *args], check=True,
                   capture_output=True)


def _git_repo(project: Path, ignore_state: bool = True,
              ignore_audit: bool = False) -> None:
    _git(project, "init", "-q")
    lines = []
    if ignore_state:
        lines.append(".ai-native/state/")
    if ignore_audit:
        lines.append(".ai-native/audit/")
    (project / ".gitignore").write_text("\n".join(lines) + "\n",
                                        encoding="utf-8")


def _candidate(identifier: str, claim: str = "A durable rule.",
               state: str = "PENDING") -> dict:
    return {"schema_version": 1, "candidate_id": identifier, "kind": "rule",
            "state": state, "created_at": "2026-09-07T00:00:00+00:00",
            "updated_at": "2026-09-07T00:00:00+00:00",
            "source": {"origin": "test"}, "scope": {"project": "demo"},
            "claim": claim,
            "identity": {"identity_key": "project/demo/rule/x",
                         "identity_key_grammar_version": 1},
            "assertion_hash": "0" * 64,
            "assertion_normalization_version": 1, "hash_algorithm": "sha256",
            "provenance": {"actor": "tester"}}


def _project(directory: str) -> Path:
    """Hermetic project: a correct git repo when git exists, else unchecked."""

    project = Path(directory)
    if GIT is not None:
        _git_repo(project)
    return project


def _hammer(args: tuple) -> tuple:
    project_str, worker, count = args
    project = Path(project_str)
    for index in range(count):
        identifier = f"cand-w{worker}-i{index}"
        storelib.append_candidate(project, _candidate(identifier))
        storelib.record_audit(project, operation="capture", actor="tester",
                              candidate_id=identifier, detail={"n": index})
    return worker, count


@unittest.skipUnless(GIT, "git executable required")
class PolicyTest(unittest.TestCase):
    def test_StateStageable_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _git_repo(project, ignore_state=False)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1"))
            self.assertEqual(caught.exception.code,
                             "KNOWLEDGE_CONTROL_PATH_POLICY_INVALID")

    def test_AuditIgnored_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _git_repo(project, ignore_audit=True)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1"))
            self.assertEqual(caught.exception.code,
                             "KNOWLEDGE_CONTROL_PATH_POLICY_INVALID")

    def test_CorrectPolicy_Writes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            _git_repo(project)
            stored = storelib.append_candidate(project, _candidate("c1"))
            self.assertEqual(stored["candidate_id"], "c1")

    def test_GitMissing_ProceedsUnchecked(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            import subprocess as subprocesslib
            original = subprocesslib.run

            def _missing(*args, **kwargs):
                raise OSError("no git here")

            subprocesslib.run = _missing
            try:
                report = controlpaths.ensure_policy(project)
            finally:
                subprocesslib.run = original
            self.assertFalse(report["enforced"])

    def test_PlantedSymlink_RefusedWithoutSideEffects(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            outside = Path(directory) / "outside"
            (project / ".ai-native").mkdir(parents=True, exist_ok=True)
            try:
                os.symlink(str(outside), project / ".ai-native" / "state")
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1"))
            self.assertEqual(caught.exception.code,
                             "KNOWLEDGE_CONTROL_PATH_POLICY_INVALID")
            self.assertFalse(outside.exists())


class ConcurrencyTest(unittest.TestCase):
    def test_ConcurrentWriters_ZeroLoss(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            workers, per_worker = 8, 5
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(
                    _hammer,
                    [(str(project), worker, per_worker)
                     for worker in range(workers)]))
            self.assertEqual(sorted(worker for worker, _ in results),
                             list(range(workers)))
            candidates = storelib.list_candidates(project)
            self.assertEqual(len(candidates), workers * per_worker)
            identifiers = {item["candidate_id"] for item in candidates}
            expected = {f"cand-w{worker}-i{index}"
                        for worker in range(workers)
                        for index in range(per_worker)}
            self.assertEqual(identifiers, expected)
            audits = [event for event in storelib.list_audit(project)
                      if "event_id" in event]
            self.assertEqual(len(audits), workers * per_worker)


class CrashTest(unittest.TestCase):
    def test_TempLeftover_Ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            storelib.append_candidate(project, _candidate("c1"))
            state = controlpaths.state_dir(project)
            (state / ".tmp-crashed").write_bytes(b"partial")
            self.assertEqual(len(storelib.list_candidates(project)), 1)
            storelib.append_candidate(project, _candidate("c2"))
            self.assertEqual(len(storelib.list_candidates(project)), 2)

    def test_TornFile_FailsClosedWithLocation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            storelib.append_candidate(project, _candidate("c1"))
            path = controlpaths.state_dir(project) / "candidates.jsonl"
            path.write_bytes(b"{torn")
            with self.assertRaises(KnowledgeError) as caught:
                storelib.list_candidates(project)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_STORE_CORRUPTED")
            self.assertIn("candidates.jsonl", str(caught.exception))

    def test_InjectedCrash_LeavesDurableState(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            storelib.append_candidate(project, _candidate("c1"))
            from ainative.lifecycle import state as statelib
            original = statelib.write_atomic

            def _crash(path, payload):
                original(path, payload)
                raise RuntimeError("injected crash after replace")

            statelib.write_atomic = _crash
            try:
                with self.assertRaises(RuntimeError):
                    storelib.append_candidate(project, _candidate("c2"))
            finally:
                statelib.write_atomic = original
            self.assertEqual(
                [item["candidate_id"] for item in storelib.list_candidates(project)],
                ["c1", "c2"])

    def test_FutureSchema_FailsClosed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            storelib.append_candidate(project, _candidate("c1"))
            path = controlpaths.state_dir(project) / "candidates.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[0])
            event["schema_version"] = 99
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaises(KnowledgeError) as caught:
                storelib.list_candidates(project)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_STORE_CORRUPTED")


class BoundsTest(unittest.TestCase):
    def test_OversizeClaim_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1", claim="x" * 5000))
            self.assertEqual(caught.exception.code, "KNOWLEDGE_MALFORMED")

    def test_OversizePayload_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            record = _candidate("c1")
            record["scope"] = {"project": "demo", "notes": "y" * 20000}
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, record)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_CANDIDATE_TOO_LARGE")

    def test_CountBound_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            limits = boundslib.Bounds(max_candidate_count=1)
            storelib.append_candidate(project, _candidate("c1"), bounds=limits)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c2"), bounds=limits)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_STORE_FULL")

    def test_Warnings_SurfaceNearBound(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            limits = boundslib.Bounds(max_candidate_count=10)
            for index in range(8):
                storelib.append_candidate(project, _candidate(f"c{index}"),
                                          bounds=limits)
            report = storelib.storage_status(project, bounds=limits)
            self.assertTrue(report["warnings"])
            self.assertEqual(report["counts"]["candidates"], 8)


class TraversalTest(unittest.TestCase):
    def test_LocatorTraversal_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            stored = storelib.append_candidate(project, _candidate("c1"))
            with self.assertRaises(KnowledgeError):
                storelib.append_support(project, {"support_id": "s1",
                                                  "candidate_id": stored["candidate_id"],
                                                  "kind": "test",
                                                  "locator": "../../escape"})
            with self.assertRaises(KnowledgeError):
                storelib.append_support(project, {"support_id": "s2",
                                                  "candidate_id": stored["candidate_id"],
                                                  "kind": "test",
                                                  "locator": "/etc/passwd"})

    def test_UnknownCandidate_NotFound(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.get_candidate(project, "nope")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_NOT_FOUND")


class QuarantineTest(unittest.TestCase):
    def test_SecretClaim_RefusedBeforeAnyWrite(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            with self.assertRaises(KnowledgeError):
                storelib.append_candidate(
                    project, _candidate("c1", claim="deploy with api_key = abc"))
            self.assertFalse((controlpaths.state_dir(project)
                              / "candidates.jsonl").exists())

    def test_AuditNestedDetail_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            with self.assertRaises(KnowledgeError):
                storelib.record_audit(project, operation="x", actor="t",
                                      detail={"nested": {"a": 1}})
            with self.assertRaises(KnowledgeError):
                storelib.record_audit(project, operation="x", actor="t",
                                      detail={"token": "auth_token = abc"})

    def test_Tombstone_SecretReason_RefusedNoRawText(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _project(directory)
            with self.assertRaises(KnowledgeError):
                storelib.append_tombstone(project, "a" * 64,
                                          reason="leaked api_key = abc",
                                          actor="t")
            marker = storelib.append_tombstone(project, "a" * 64,
                                               reason="superseded",
                                               actor="t")
            self.assertEqual(marker["assertion_hash"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
