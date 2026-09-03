import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ainative_workplane.contracts import generate_uid
from ainative_workplane.trust import policy_commitment
from ainative_workplane.controller import ControllerError, WorkController

DIGEST = "a" * 64


def policy():
    """A minimal policy that requires nothing observable, stated explicitly."""

    declared = {
        "schema_name": "project_policy", "schema_version": 1,
        "approval_predicate": {"predicate_id": "review", "policy_digest": DIGEST},
        "required_mutation_facts": {}, "required_evidence_facts": {},
        "waiver_approval_rule": {"predicate_id": "waiver", "policy_digest": DIGEST},
        "human_approval_rule": {"predicate_id": "human", "policy_digest": DIGEST},
        "promotion_policy": "explicit",
    }
    commitment = policy_commitment(declared)
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        declared[field]["policy_digest"] = commitment
    return declared, commitment


def approval_for(controller, candidate, commitment):
    return {
        "schema_name": "mutation_approval", "schema_version": 1, "uid": generate_uid("approval"),
        "target_digest": controller.normative_digest(candidate), "policy_digest": commitment,
        "predicate_id": "review", "approved_by": "test", "approved_at": "2026-09-03T00:00:00Z",
        "provenance": "GIT_RECORDED",
    }


def requirement(statement="the system refuses unbound evidence"):
    criterion = generate_uid("ac")
    return {"schema_name": "requirements", "schema_version": 1, "uid": generate_uid("req"), "statement": statement, "acceptance_criteria": [{"uid": criterion, "digest": DIGEST}]}


def task(paths=("src/app.py",)):
    return {"schema_name": "tasks", "schema_version": 1, "uid": generate_uid("task"), "requirements": [{"uid": generate_uid("req"), "digest": DIGEST}], "implementation_paths": list(paths)}


class WorkControllerTests(unittest.TestCase):
    def test_create_mutate_and_detect_direct_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            first = controller.create({"notes": {"value": "initial"}})
            self.assertEqual(1, first["revision"])
            self.assertEqual(1, controller.read()["revision"])
            second = controller.mutate(1, {"notes": {"value": "next"}})
            self.assertEqual(2, second["revision"])
            with self.assertRaisesRegex(ControllerError, "STALE_REVISION"):
                controller.mutate(1, {"notes": {"value": "stale"}})
            pointer = second["artifacts"]["notes"]
            path = Path(directory) / pointer["path"]
            path.write_text('{"value":"tampered"}', encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "UNEXPECTED_MUTATION"):
                controller.read()

    def test_manifest_is_last_commit_marker_and_staging_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            controller.create({"notes": {"done": False}})
            self.assertTrue((Path(directory) / "manifest.json").is_file())
            self.assertEqual(0, controller.recover_staging())
            with self.assertRaisesRegex(ControllerError, "WORK_ALREADY_EXISTS"):
                controller.create({"notes": {"done": True}})

    def hold_lock(self, controller, *, pid, host):
        controller.root.mkdir(parents=True, exist_ok=True)
        controller.lock_path.write_text(json.dumps({"pid": pid, "host": host, "created_at": "2026-09-02T00:00:00Z", "transaction_id": "held"}), encoding="utf-8")

    def test_concurrent_writer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            self.hold_lock(controller, pid=os.getpid(), host=socket.gethostname())
            with self.assertRaisesRegex(ControllerError, "CONCURRENT_WRITER"):
                controller.create({"notes": {"done": False}})

    def test_dead_writer_lock_is_reclaimed_but_live_and_foreign_locks_are_not(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            controller.create({"notes": {"revision": 1}})

            crashed = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            crashed.kill()
            crashed.wait()
            self.hold_lock(controller, pid=crashed.pid, host=socket.gethostname())
            self.assertEqual(2, controller.mutate(1, {"notes": {"revision": 2}})["revision"])
            self.assertFalse(controller.lock_path.exists())

            self.hold_lock(controller, pid=os.getpid(), host="another-machine")
            with self.assertRaisesRegex(ControllerError, "CONCURRENT_WRITER"):
                controller.mutate(2, {"notes": {"revision": 3}})

            live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                self.hold_lock(controller, pid=live.pid, host=socket.gethostname())
                with self.assertRaisesRegex(ControllerError, "CONCURRENT_WRITER"):
                    controller.mutate(2, {"notes": {"revision": 3}})
            finally:
                live.kill()
                live.wait()

            controller.lock_path.write_text("not a lock record", encoding="utf-8")
            with self.assertRaisesRegex(ControllerError, "INVALID_LOCK"):
                controller.mutate(2, {"notes": {"revision": 3}})
            self.assertEqual(2, WorkController(directory).read()["revision"])

    def test_crash_before_manifest_preserves_previous_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            WorkController(directory).create({"notes": {"revision": 1}})
            def crash(step):
                if step == "after_promotion_before_manifest":
                    raise RuntimeError("injected crash")
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                WorkController(directory, failure_injector=crash).mutate(1, {"notes": {"revision": 2}})
            self.assertEqual(1, WorkController(directory).read()["revision"])
            recovered = WorkController(directory).recover_staging()
            self.assertEqual(1, recovered)
            self.assertFalse((Path(directory) / "revisions" / "2").exists())

    def test_recovery_discards_orphan_revision_before_first_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            orphan = root / "revisions" / "1"
            orphan.mkdir(parents=True)
            (orphan / "notes.json").write_text('{"orphan":true}', encoding="utf-8")
            manifest = WorkController(directory).create({"notes": {"fresh": True}})
            self.assertEqual(1, manifest["revision"])
            self.assertEqual({"fresh": True}, json.loads((root / "revisions" / "1" / "notes.json").read_text(encoding="utf-8")))



    def test_a64_a_normative_artifact_without_a_schema_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            for name in ("requirements", "tasks", "project_policy", "approval_root"):
                with self.subTest(artifact=name):
                    with self.assertRaisesRegex(ControllerError, "INVALID_NORMATIVE_ARTIFACT"):
                        WorkController(Path(directory) / name).create({name: {"whatever": True}})
            # A name outside the normative set is storable, and marked as such.
            manifest = controller.create({"scratch": {"whatever": True}})
            self.assertFalse(manifest["artifacts"]["scratch"]["normative"])

    def test_a63_a_partial_mutation_preserves_every_other_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkController(directory)
            declared, commitment = policy()
            first = requirement()
            original_task = task()
            committed = {"requirements": [first], "tasks": [original_task], "project_policy": declared, "scratch": {"note": "keep me"}}
            controller.create(committed)

            replacement = task(paths=["src/other.py"])
            candidate = {**committed, "tasks": [replacement]}
            controller.mutate(1, {"tasks": [replacement]}, approval=approval_for(controller, candidate, commitment))
            manifest, artifacts = WorkController(directory).load_committed_artifacts()
            self.assertEqual(2, manifest["revision"])
            self.assertEqual({"requirements", "tasks", "project_policy", "scratch"}, set(artifacts))
            self.assertEqual([first], artifacts["requirements"], "a partial mutation deleted a normative artifact")
            self.assertEqual([replacement], artifacts["tasks"])
            self.assertEqual({"note": "keep me"}, artifacts["scratch"])
            self.assertTrue(manifest["artifacts"]["requirements"]["normative"])

            after_delete = {name: value for name, value in artifacts.items() if name != "requirements"}
            controller.mutate(2, delete_artifacts=["requirements"], approval=approval_for(controller, after_delete, commitment))
            _, remaining = WorkController(directory).load_committed_artifacts()
            self.assertEqual({"tasks", "project_policy", "scratch"}, set(remaining))

            with self.assertRaisesRegex(ControllerError, "UNKNOWN_ARTIFACT"):
                controller.mutate(3, delete_artifacts=["never_committed"])


if __name__ == "__main__":
    unittest.main()
