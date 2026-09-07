"""PR4 gates: fail-closed quarantine on every persistence surface."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from ainative.knowledge import bounds as boundslib
from ainative.knowledge import paths as controlpaths
from ainative.knowledge import quarantine as quarantinelib
from ainative.knowledge import store as storelib
from ainative.knowledge.errors import KnowledgeError

SECRET = "deploy with api_key = abc123XYZ"


def _repo(directory: str) -> Path:
    import shutil
    if shutil.which("git") is None:
        raise unittest.SkipTest("git executable required")
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True,
                   capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    return project


def _candidate(identifier: str, claim: str = "A durable rule.") -> dict:
    return {"schema_version": 1, "candidate_id": identifier, "kind": "rule",
            "state": "PENDING", "created_at": "2026-09-07T00:00:00+00:00",
            "updated_at": "2026-09-07T00:00:00+00:00",
            "source": {"origin": "test"}, "scope": {"project": "demo"},
            "claim": claim,
            "identity": {"identity_key": "project/demo/rule/x",
                         "identity_key_grammar_version": 1},
            "assertion_hash": "0" * 64,
            "assertion_normalization_version": 1, "hash_algorithm": "sha256",
            "provenance": {"actor": "tester"}}


class FakeScanner:
    def __init__(self, available: bool = True, crash: bool = False,
                 flag: str = "STRONGBAD") -> None:
        self._available = available
        self._crash = crash
        self._flag = flag

    @property
    def available(self) -> bool:
        return self._available

    def scan(self, text: str):
        if self._crash:
            raise RuntimeError("scanner down")
        if isinstance(text, str) and self._flag in text:
            return "strong"
        return None


class QuarantineTest(unittest.TestCase):
    def test_SecretInClaim_RefusedBeforePersistence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1", SECRET))
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")
            self.assertNotIn("abc123", str(caught.exception))
            self.assertFalse((controlpaths.state_dir(project)
                              / "candidates.jsonl").exists())

    def test_SecretInStructuredValue_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = _candidate("c1")
            record["assertion_value"] = {"type": "string",
                                         "value": "token is auth_token = abc"}
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, record)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_SecretInSupport_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            storelib.append_candidate(project, _candidate("c1"))
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_support(project, {"support_id": "s1",
                                                  "candidate_id": "c1",
                                                  "kind": "note",
                                                  "locator": "notes.md",
                                                  "note": SECRET})
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_SecretInProvenance_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            record = _candidate("c1")
            record["provenance"] = {"actor": "tester", "note": SECRET}
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, record)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_SecretInTombstoneReason_Refused(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_tombstone(project, "a" * 64,
                                          reason="leaked " + SECRET,
                                          actor="t")
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_SecretInAuditDetail_RefusedClean(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.record_audit(project, operation="note", actor="t",
                                      detail={"key": SECRET})
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")
            audit = controlpaths.audit_dir(project) / "audit.jsonl"
            if audit.exists():
                self.assertNotIn("abc123", audit.read_bytes().decode("utf-8"))

    def test_StrongScanner_FlagsMore(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            scanner = FakeScanner()
            record = _candidate("c1", claim="Rule mentions STRONGBAD token.")
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, record, scanner=scanner)
            self.assertEqual(caught.exception.code, "KNOWLEDGE_SECRET_REFUSED")

    def test_UnavailableScanner_RefusesWithZeroBytes(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            scanner = FakeScanner(available=False)
            before = storelib.storage_status(project)["total_bytes"]
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1"),
                                          scanner=scanner)
            self.assertEqual(caught.exception.code,
                             "KNOWLEDGE_SECRET_SCANNER_UNAVAILABLE")
            self.assertEqual(storelib.storage_status(project)["total_bytes"],
                             before)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.record_audit(project, operation="note", actor="t",
                                      scanner=scanner)
            self.assertEqual(caught.exception.code,
                             "KNOWLEDGE_SECRET_SCANNER_UNAVAILABLE")

    def test_CrashingScanner_FailsClosed(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            scanner = FakeScanner(crash=True)
            with self.assertRaises(KnowledgeError) as caught:
                storelib.append_candidate(project, _candidate("c1"),
                                          scanner=scanner)
            self.assertEqual(caught.exception.code,
                             "KNOWLEDGE_SECRET_SCANNER_UNAVAILABLE")
            self.assertEqual(storelib.list_candidates(project), [])

    def test_SafeContent_PersistsNormally(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            stored = storelib.append_candidate(project, _candidate("c1"))
            self.assertEqual(stored["candidate_id"], "c1")
            event = storelib.record_audit(project, operation="capture",
                                          actor="tester",
                                          candidate_id="c1",
                                          detail={"n": 1})
            self.assertEqual(event["operation"], "capture")


if __name__ == "__main__":
    unittest.main()
