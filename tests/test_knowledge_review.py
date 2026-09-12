"""Review queue: advisory exposure, honest K5/trust status, zero writes."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ainative.knowledge import imports as importslib
from ainative.knowledge import review as reviewlib
from ainative.knowledge import store as storelib


def _repo(directory: str) -> Path:
    project = Path(directory)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True, capture_output=True)
    (project / ".gitignore").write_text(".ai-native/state/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True, capture_output=True)
    return project


def _apply(project: Path, root: Path, slug: str, item: dict):
    source = root / "items.json"
    source.write_text(json.dumps([item]), encoding="utf-8")
    return importslib.apply(project, source, harness="claude", project_slug=slug)


class ReviewQueueTests(unittest.TestCase):
    def test_conflict_entries_rank_first_and_list_holders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "reviewsandbox"
            key = f"project/{slug}/workflow/review"
            _apply(project, root, slug, {"claim": "review happens on Fridays", "identity_key": key})
            _apply(project, root, slug, {"claim": "review happens on Mondays", "identity_key": key})
            report = reviewlib.review_queue(project)
            self.assertEqual(2, len(report["queue"]))
            first = report["queue"][0]
            self.assertEqual(3, first["review_priority"])
            self.assertEqual("NEEDS_HUMAN", first["outcome"])
            self.assertEqual(1, len(first["holders"]))
            conflicts = reviewlib.conflicts(project)
            self.assertEqual(2, conflicts["count"])

    def test_unique_priority_depends_on_support(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "reviewsandbox"
            applied = _apply(project, root, slug,
                             {"claim": "workflow review happens on Fridays",
                              "identity_key": f"project/{slug}/workflow/review"})
            report = reviewlib.review_queue(project)
            self.assertEqual(2, report["queue"][0]["review_priority"])
            self.assertEqual("NEEDS_EVIDENCE", report["queue"][0]["outcome"])
            target = applied["created"][0]
            with mock.patch.object(reviewlib.storelib, "list_supports",
                                   return_value=[{"candidate_id": target, "kind": "test"}]):
                report = reviewlib.review_queue(project)
            self.assertEqual(1, report["queue"][0]["review_priority"])
            self.assertEqual("ADD", report["queue"][0]["outcome"])

    def test_status_fields_are_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            project = _repo(directory)
            report = reviewlib.review_queue(project)
            self.assertEqual("TRUSTED_OPERATOR_CEREMONY", report["trust"]["approval_mode"])
            self.assertEqual("UNVERIFIED", report["trust"]["qualification"])
            self.assertEqual("GATE_CLOSED", report["promotion"]["eligibility"])
            self.assertEqual("NOT_APPLICABLE", report["representation_health"])

    def test_queue_is_sorted_by_priority_descending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "reviewsandbox"
            key = f"project/{slug}/workflow/review"
            _apply(project, root, slug, {"claim": "review happens on Fridays", "identity_key": key})
            _apply(project, root, slug, {"claim": "review happens on Mondays", "identity_key": key})
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/convention"})
            report = reviewlib.review_queue(project)
            priorities = [item["review_priority"] for item in report["queue"]]
            self.assertEqual(sorted(priorities, reverse=True), priorities)
            self.assertEqual(1, report["counts"].get("NEEDS_EVIDENCE", 0))

    def test_review_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _repo(directory)
            slug = "reviewsandbox"
            _apply(project, root, slug, {"claim": "workflow review happens on Fridays",
                                         "identity_key": f"project/{slug}/workflow/review"})
            candidates = project / ".ai-native" / "state" / "knowledge" / "candidates.jsonl"
            before = candidates.read_bytes()
            reviewlib.review_queue(project)
            reviewlib.conflicts(project)
            self.assertEqual(before, candidates.read_bytes())


if __name__ == "__main__":
    unittest.main()
