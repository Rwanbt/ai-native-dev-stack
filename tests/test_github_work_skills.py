"""Executable helpers behind the GitHub work skills: claims and AC guard.

docs/GITHUB-WORKFLOW.md makes two procedures deterministic instead of
prose-only, because two agents following prose can both "win":

    claim_resolution  — who proceeds when several actors claimed one Issue
    ac_guard          — whether an Issue's Acceptance Criteria drifted

These tests pin the decision tables. The helpers are pure and stdlib-only;
they are loaded by path because they ship with the skills tree, not as a
package. The SkillContract cases pin the fail-closed rules that stay
procedural (Markdown) so a doc edit cannot silently remove a guard.
"""

from __future__ import annotations

import importlib.util
import re
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
    """Claim arbitration: each actor is represented by their EARLIEST valid
    claim event. Assignment preference is an acquisition rule, never an
    arbitration override — a later assignment cannot erase an actor's
    earlier comment chronology."""

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

    def test_same_actor_signals_collapse_into_their_earliest_event(self) -> None:
        # One actor signalling twice is one claimant, represented by their
        # earliest observable claim — here the comment, not the later
        # assignment. Preference is acquisition guidance, not arbitration.
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "2026-09-05T10:00:00Z", 201),
            signal("assignment", "alice", "2026-09-05T10:05:00Z", 205),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["kind"], "comment")
        self.assertEqual(verdict["winner"]["created_at"], "2026-09-05T10:00:00Z")
        self.assertEqual(verdict["losers"], [])

    def test_late_assignment_cannot_erase_earlier_comment_chronology(self) -> None:
        # The regression that motivated P1-03: a 12:00 assignment must not
        # rewrite Alice's 09:00 comment into a losing position.
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "2026-09-05T09:00:00Z", 100),
            signal("comment", "bob", "2026-09-05T10:00:00Z", 101),
            signal("assignment", "alice", "2026-09-05T12:00:00Z", 102),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["actor"], "alice")
        self.assertEqual(verdict["winner"]["created_at"], "2026-09-05T09:00:00Z")
        self.assertEqual([loser["actor"] for loser in verdict["losers"]], ["bob"])

    def test_assignment_first_still_wins_when_it_is_the_earliest(self) -> None:
        verdict = claim_resolution.resolve([
            signal("assignment", "alice", "2026-09-05T09:00:00Z", 100),
            signal("comment", "alice", "2026-09-05T10:00:00Z", 101),
            signal("comment", "bob", "2026-09-05T11:00:00Z", 102),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["actor"], "alice")
        self.assertEqual(verdict["winner"]["created_at"], "2026-09-05T09:00:00Z")

    def test_earlier_assignment_from_another_actor_wins(self) -> None:
        # A comment at 10:00 loses to an assignment at 09:00 — kind confers
        # no temporal priority in either direction.
        verdict = claim_resolution.resolve([
            signal("comment", "alice", "2026-09-05T10:00:00Z", 200),
            signal("assignment", "bob", "2026-09-05T09:00:00Z", 201),
        ])
        self.assertEqual(verdict["status"], claim_resolution.PROCEED)
        self.assertEqual(verdict["winner"]["actor"], "bob")

    def test_assignment_loses_to_earlier_comment_from_another_actor(self) -> None:
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
        # Case is collapsed for identity; the reported actor keeps the case
        # of the representative (earliest) signal.
        self.assertEqual(verdict["winner"]["actor"].lower(), "alice")
        self.assertEqual(verdict["winner"]["created_at"], "2026-09-05T10:00:00Z")


class AcGuard(unittest.TestCase):
    """The AC contract: the digest covers the COMPLETE semantic content of
    every criterion — its checkbox line, its continuation lines and its
    nested bullets. Checkbox state, CRLF and template comments are noise;
    everything else is contract. Binding an Issue without usable AC is
    refused; checking never silently passes."""

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

    RICH_BODY = (
        "## Problem\n"
        "Authentication is inconsistent.\n"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        "<!-- one observable behavior per item -->\n"
        "- [ ] Invalid authentication must:\n"
        "  - return HTTP 401\n"
        "  - never expose a stack trace\n"
        "- [x] The login page must:\n"
        "  show a single error message that names the failed factor\n"
        "\n"
        "## Out of scope\n"
        "- session revocation\n"
    )

    # --- extraction and digest stability ---------------------------------

    def test_extracts_criteria_in_order(self) -> None:
        self.assertEqual(ac_guard.extract(self.BODY), [
            "the widget closes its file handle on error paths",
            "regression test covers the leak",
            "docs mention the behavior",
        ])

    def test_multiline_criterion_includes_continuation_and_nested_bullets(self) -> None:
        self.assertEqual(ac_guard.extract(self.RICH_BODY), [
            "Invalid authentication must: - return HTTP 401 - never expose a stack trace",
            "The login page must: show a single error message that names the failed factor",
        ])

    def test_digest_ignores_checkbox_state(self) -> None:
        # Ticking boxes during implementation is progress, not drift.
        done = self.BODY.replace("- [ ] the widget closes", "- [x] the widget closes")
        self.assertEqual(ac_guard.digest(self.BODY), ac_guard.digest(done))

    def test_digest_ignores_checkbox_state_on_multiline_criteria(self) -> None:
        done = self.RICH_BODY.replace("- [ ] Invalid authentication must:",
                                      "- [x] Invalid authentication must:")
        self.assertEqual(ac_guard.digest(self.RICH_BODY), ac_guard.digest(done))

    def test_digest_ignores_checkbox_style_and_wrapping(self) -> None:
        variant = self.BODY.replace("- [x] regression", "* [X]  regression")
        self.assertEqual(ac_guard.digest(self.BODY), ac_guard.digest(variant))

    def test_digest_ignores_crlf_line_endings(self) -> None:
        self.assertEqual(ac_guard.digest(self.RICH_BODY),
                         ac_guard.digest(self.RICH_BODY.replace("\n", "\r\n")))

    def test_digest_ignores_template_comments(self) -> None:
        without_comment = self.RICH_BODY.replace("<!-- one observable behavior per item -->\n", "")
        self.assertEqual(ac_guard.digest(self.RICH_BODY), ac_guard.digest(without_comment))

    def test_digest_ignores_multiline_template_comments(self) -> None:
        commented = self.BODY.replace(
            "## Acceptance criteria\n",
            "## Acceptance criteria\n<!--\ntriage guidance here\n-->\n")
        self.assertEqual(ac_guard.digest(self.BODY), ac_guard.digest(commented))

    def test_digest_ignores_indentation_style(self) -> None:
        four_space = self.RICH_BODY.replace("  - return HTTP 401",
                                            "      - return HTTP 401")
        self.assertEqual(ac_guard.digest(self.RICH_BODY), ac_guard.digest(four_space))

    # --- semantic drift on multiline / nested criteria --------------------

    def test_continuation_line_edit_is_drift(self) -> None:
        # The exact flip the invariant exists for: "never expose" -> "include".
        flipped = self.RICH_BODY.replace("never expose a stack trace",
                                         "include the stack trace")
        verdict = ac_guard.check(flipped, ac_guard.digest(self.RICH_BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_nested_bullet_change_is_drift(self) -> None:
        changed = self.RICH_BODY.replace("- return HTTP 401", "- return HTTP 403")
        verdict = ac_guard.check(changed, ac_guard.digest(self.RICH_BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_nested_bullet_removal_is_drift(self) -> None:
        removed = self.RICH_BODY.replace("  - never expose a stack trace\n", "")
        verdict = ac_guard.check(removed, ac_guard.digest(self.RICH_BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_single_line_criterion_edit_is_drift(self) -> None:
        changed = self.BODY.replace("docs mention the behavior",
                                    "docs mention the behavior in the glossary")
        verdict = ac_guard.check(changed, ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_criterion_removal_is_drift(self) -> None:
        shortened = self.BODY.replace("- [ ] docs mention the behavior\n", "")
        self.assertEqual(ac_guard.check(shortened, ac_guard.digest(self.BODY))["verdict"],
                         "ISSUE_CHANGED")

    def test_criterion_addition_is_drift(self) -> None:
        grown = self.BODY.replace("- [ ] docs mention the behavior\n",
                                  "- [ ] docs mention the behavior\n"
                                  "- [ ] changelog entry added\n")
        verdict = ac_guard.check(grown, ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_criterion_reordering_is_drift(self) -> None:
        reordered = self.BODY.replace(
            "- [ ] the widget closes its file handle on error paths\n"
            "- [x] regression test covers the leak\n",
            "- [x] regression test covers the leak\n"
            "- [ ] the widget closes its file handle on error paths\n")
        verdict = ac_guard.check(reordered, ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_losing_the_ac_section_is_drift(self) -> None:
        verdict = ac_guard.check("## Problem\nnothing to see\n",
                                 ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")

    def test_matching_digest_is_ok(self) -> None:
        self.assertEqual(ac_guard.check(self.BODY, ac_guard.digest(self.BODY))["verdict"],
                         "OK")
        self.assertEqual(ac_guard.check(self.RICH_BODY, ac_guard.digest(self.RICH_BODY))["verdict"],
                         "OK")

    def test_unbound_guard_is_drift_not_silent_pass(self) -> None:
        verdict = ac_guard.check(self.BODY, "")
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")
        self.assertIn("no bound digest", verdict["reason"])

    # --- fail-closed binding ----------------------------------------------

    def test_bind_of_valid_bodies_returns_digest_and_criteria(self) -> None:
        bound = ac_guard.bind(self.BODY)
        self.assertEqual(bound["digest"], ac_guard.digest(self.BODY))
        self.assertEqual(len(bound["criteria"]), 3)

    def test_bind_without_heading_is_invalid(self) -> None:
        verdict = ac_guard.bind("## Problem\nnothing to see\n")
        self.assertEqual(verdict["verdict"], "INVALID_ACCEPTANCE_CRITERIA")
        self.assertIn("heading", verdict["reason"])

    def test_bind_with_heading_but_no_checkbox_is_invalid(self) -> None:
        verdict = ac_guard.bind(
            "## Acceptance criteria\n\nThe work is described in prose only.\n")
        self.assertEqual(verdict["verdict"], "INVALID_ACCEPTANCE_CRITERIA")
        self.assertIn("checkbox", verdict["reason"])

    def test_check_on_body_that_lost_its_ac_is_never_ok(self) -> None:
        verdict = ac_guard.check("## Problem\nthe AC was deleted\n",
                                 ac_guard.digest(self.BODY))
        self.assertEqual(verdict["verdict"], "ISSUE_CHANGED")
        self.assertTrue(verdict["reason"])


class SkillContract(unittest.TestCase):
    """The procedural guards stay pinned: a doc edit cannot silently
    remove a fail-closed rule (ACTIVE_PR_CONFLICT, AC grammar, triage
    decomposition invariants)."""

    SKILL = (REPO / "skills" / "issue-to-implementation" / "SKILL.md").read_text(encoding="utf-8")
    TRIAGE = (REPO / "skills" / "github-triage" / "SKILL.md").read_text(encoding="utf-8")

    def test_open_linked_pr_is_a_claim_level_conflict(self) -> None:
        self.assertIn("ACTIVE_PR_CONFLICT", self.SKILL)
        self.assertRegex(self.SKILL, r"ACTIVE_PR_CONFLICT[\s\S]{0,400}STOP")
        # The conflict check must happen BEFORE the claim attempt, and the
        # race must be re-checked after claiming.
        read_step = self.SKILL.index("Read the claim state")
        claim_step = self.SKILL.index("Attempt a visible claim")
        self.assertLess(read_step, claim_step)

    def test_open_pr_conflict_exceptions_are_explicit(self) -> None:
        self.assertIn("maintainer requested", self.SKILL.lower())
        self.assertIn("same actor", self.SKILL.lower())
        self.assertIn("abandoned", self.SKILL.lower())
        self.assertIn("age", self.SKILL.lower())

    def test_phase_step_numbers_have_no_duplicates(self) -> None:
        for phase in re.split(r"^## ", self.SKILL, flags=re.MULTILINE)[1:]:
            numbers = [int(m.group(1)) for m in re.finditer(r"^\s*(\d+)\. \*\*", phase, re.MULTILINE)]
            self.assertEqual(sorted(numbers), sorted(set(numbers)),
                             f"duplicate step numbers in phase: {phase.splitlines()[0]}")

    def test_ac_grammar_requires_a_usable_criterion(self) -> None:
        self.assertIn("at least one checkbox criterion", self.SKILL)
        self.assertIn("continuation", self.SKILL.lower())

    def test_triage_separates_type_priority_and_decomposition(self) -> None:
        self.assertIn("decomposition", self.TRIAGE.lower())
        self.assertIn("does not lower severity", self.TRIAGE.lower())
        self.assertIn("umbrella", self.TRIAGE.lower())

    def test_triage_keeps_broad_actionable_work_actionable(self) -> None:
        self.assertIn("type:research", self.TRIAGE)
        self.assertRegex(self.TRIAGE, r"(?i)umbrella[\s\S]{0,600}(?:child Issues|decompos)")


if __name__ == "__main__":
    unittest.main()