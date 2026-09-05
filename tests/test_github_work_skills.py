"""Executable helpers behind the GitHub work skills: claims and AC guard.

docs/GITHUB-WORKFLOW.md makes two procedures deterministic instead of
prose-only, because two agents following prose can both "win":

    claim_resolution  — who proceeds when several actors claimed one Issue
    ac_guard          — whether an Issue's Acceptance Criteria drifted

These tests pin the decision tables. The helpers are pure and stdlib-only;
they are loaded by path because they ship with the skills tree, not as a
package.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "skills" / "issue-to-implementation" / "bin"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


claim_resolution = _load("claim_resolution")
ac_guard = _load("ac_guard")


def signal(kind: str, actor: str, created_at: str, identifier) -> dict:
    return {"kind": kind, "actor": actor, "created_at": created_at,
            "identifier": identifier}


class ClaimResolution(unittest.TestCase):
    """The decision table from docs/GITHUB-WORKFLOW.md, "Multi-agent claims"."""

    def test_zero_valid_claims_is_claim_failed(self) -> None:
        verdict = claim_resolution.resolve([])
        self.assertEqual(verdict["status"], claim_resolution.CLAIM_FAILED)
        self.assertIsNone(verdict["winner"])

    def test_invalid_signals_are_noise_not_claims(self) -> None:
        garbage = [{"kind": "comment"}, {"actor": "a"},
                   "not a dict", {"kind": "comment", "actor": "", "created_at": "t",
                                  "identifier": 1}]
        self.assertEqual(claim_resolution.resolve(garbage)["status"],
                         claim_resolution.CLAIM_FAILED)

    def test_single_assignment_proceeds(self) -> None:
        verdict = claim_resolution.resolve(
            [signal("assignment", "alice", "2026-09-05T10:00:00Z", 100)])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["actor"], "alice")
        self.assertEqual(verdict["losers"], [])

    def test_two_comments_earliest_timestamp_wins(self) -> None:
        verdict = claim_resolution.resolve([
            signal("comment", "late", "2026-09-05T11:00:00Z", 202),
            signal("comment", "early", "2026-09-05T10:00:00Z", 201),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["actor"], "early")
        self.assertEqual([loser["actor"] for loser in verdict["losers"]], ["late"])

    def test_timestamp_tie_is_broken_by_identifier(self) -> None:
        verdict = claim_resolution.resolve([
            signal("comment", "higher-id", "2026-09-05T10:00:00Z", 202),
            signal("comment", "lower-id", "2026-09-05T10:00:00Z", 201),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["actor"], "lower-id")
        self.assertEqual(verdict["reason"], "deterministic order: created_at, then identifier")

    def test_duplicate_ordering_key_is_a_conflict(self) -> None:
        # Same timestamp AND same identifier for two actors: no stable rule
        # can pick a winner, so every claimant must stop.
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "2026-09-05T10:00:00Z", 201),
            signal("comment", "bob", "2026-09-05T10:00:00Z", 201),
        ])
        self.assertEqual(verdict["status"], claim_resolution.CLAIM_CONFLICT)

    def test_assignment_and_comment_from_one_actor_are_one_claim(self) -> None:
        # The same actor signalling twice is one claimant — and the
        # assignment (the preferred form) represents it.
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "2026-09-05T10:00:00Z", 201),
            signal("assignment", "alice", "2026-09-05T10:05:00Z", 205),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["kind"], "assignment")
        self.assertEqual(verdict["losers"], [])

    def test_assignment_loses_to_earlier_comment_from_another_actor(self) -> None:
        # Preference selects the representative signal; it does not outrank
        # another actor's earlier claim.
        verdict = claim_resolution.resolve([
            signal("assignment", "late-assignee", "2026-09-05T12:00:00Z", 300),
            signal("comment", "early-commenter", "2026-09-05T09:00:00Z", 200),
        ])
        self.assertEqual(verdict["winner"]["actor"], "early-commenter")

    def test_missing_timestamp_is_indeterminate(self) -> None:
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "", 201),
            signal("comment", "bob", "2026-09-05T10:00:00Z", 202),
        ])
        self.assertEqual(verdict["status"], claim_resolution.CLAIM_CONFLICT)

    def test_mixed_identifier_types_are_a_conflict_not_a_crash(self) -> None:
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "2026-09-05T10:00:00Z", 201),
            signal("comment", "bob", "2026-09-05T10:00:00Z", "202"),
        ])
        self.assertEqual(verdict["status"], claim_resolution.CLAIM_CONFLICT)

    def test_actor_case_is_collapsed_for_deduplication(self) -> None:
        verdict = claim_resolution.resolve([
            signal("comment", "Alice", "2026-09-05T10:00:00Z", 201),
            signal("assignment", "alice", "2026-09-05T10:05:00Z", 205),
        ])
        self.assertEqual(verdict["winner"]["kind"], "assignment")


class AcGuard(unittest.TestCase):
    """The AC contract: content-addressed, checkbox-independent, fail-closed."""

    BODY = (
        "## Problem\n"
        "The widget leaks.\n"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        "- [ ] the widget closes its file handle on error paths\n"
        "- [x] regression test covers the leak\n"
        "- [ ] docs mention the behavior\n"
        "\n"
        "## Out of scope\n"
        "- the whole widget rewrite\n"
    )

    def test_extracts_criteria_in_order(self) -> None:
        self.assertEqual(ac_guard.extract(self.BODY), [
            "the widget closes its file handle on error paths",
            "regression test covers the leak",
            "docs mention the behavior",
        ])

    def test_digest_ignores_checkbox_state(self) -> None:
        # Ticking boxes during implementation is progress, not drift.
        done = self.BODY.replace("- [ ] the widget closes", "- [x] the widget closes")
        self.assertEqual(ac_guard.digest(self.BODY), ac_guard.digest(done))

    def test_digest_ignores_checkbox_style_and_wrapping(self) -> None:
        variant = self.BODY.replace("- [x] regression", "* [X]  regression")
        self.assertEqual(ac_guard.digest(self.BODY), ac_guard.digest(variant))

    def test_editing_a_criterion_is_drift(self) -> None:
        changed = self.BODY.replace("docs mention the behavior",
                                    "docs mention the behavior in the glossary")
        verdict = ac_guard.check(changed, ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_removing_a_criterion_is_drift(self) -> None:
        shortened = self.BODY.replace("- [ ] docs mention the behavior\n", "")
        self.assertEqual(ac_guard.check(shortened, ac_guard.digest(self.BODY))["verdict"],
                         "ISSUE_CHANGED")

    def test_losing_the_ac_section_is_drift(self) -> None:
        verdict = ac_guard.check("## Problem\nnothing to see\n",
                                 ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_matching_digest_is_ok(self) -> None:
        self.assertEqual(ac_guard.check(self.BODY, ac_guard.digest(self.BODY))["verdict"],
                         "OK")

    def test_unbound_guard_is_drift_not_silent_pass(self) -> None:
        verdict = ac_guard.check(self.BODY, "")
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")
        self.assertIn("no bound digest", verdict["reason"])

    def test_body_without_ac_section_binds_the_empty_digest(self) -> None:
        self.assertEqual(ac_guard.extract("## Problem\nno ac here\n"), [])
        self.assertEqual(len(ac_guard.digest("## Problem\nno ac here\n")), 64)


if __name__ == "__main__":
    unittest.main()