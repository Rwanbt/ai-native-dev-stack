"""Managed GitHub templates: the ownership contract, made executable.

docs/GITHUB-WORKFLOW.md, "Templates": the stack ships generic contribution
templates into a project's `.github/` — as individually tracked files, never
by claiming the directory. These tests pin the exact behavior a user must be
able to rely on when the installer touches a directory they may own:

    pre-existing user file          -> preserved, reported, never tracked
    AI-created + unchanged          -> idempotent, updatable, removable
    AI-created + user modified      -> preserved and reported as a conflict
    --dry-run                       -> no filesystem mutation at all
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.lifecycle_support import LifecycleTestCase, write_text

BUG_V1 = "# bug template v1\n"
BUG_V2 = "# bug template v2\n"
BUG_USER = "# my team's bug template, do not touch\n"
PR_V1 = "# pr template v1\n"
FEATURE_V1 = "# feature template v1\n"

TEMPLATE_PATHS = {
    "bug": ".github/ISSUE_TEMPLATE/bug.md",
    "feature": ".github/ISSUE_TEMPLATE/feature.md",
    "pr": ".github/PULL_REQUEST_TEMPLATE.md",
}

CONTENTS = {".github/ISSUE_TEMPLATE/bug.md": BUG_V1,
            ".github/ISSUE_TEMPLATE/feature.md": FEATURE_V1,
            ".github/PULL_REQUEST_TEMPLATE.md": PR_V1}


def distribution_relative(destination: str) -> str:
    """templates/github/<name> mirrors the destination minus the .github/ prefix."""

    assert destination.startswith(".github/")
    return destination[len(".github/"):]


def seed_distribution(root: Path) -> None:
    """The three templates in the synthetic distribution, as a release ships them."""

    for relative in TEMPLATE_PATHS.values():
        write_text(root / "templates" / "github" / distribution_relative(relative),
                   CONTENTS[relative])


class GithubTemplateOwnership(LifecycleTestCase):
    """Every test starts from a distribution that ships the three templates."""

    def setUp(self) -> None:
        super().setUp()
        seed_distribution(self.distribution_root)

    # --- helpers ---------------------------------------------------------

    def template_changes(self, result):
        return [change for change in result.plan.changes
                if change.component == "github-templates"]

    def tracked_template_paths(self) -> list[str]:
        state = self.state()
        if state is None:
            return []
        return [entry.path for entry in state.files_for_component("github-templates")]

    def seeded(self) -> None:
        self.install("standard")

    def user_writes(self, relative: str, content: str) -> None:
        write_text(self.project / relative, content)

    def distribution_sets(self, key: str, content: str) -> None:
        write_text(self.distribution_root / "templates" / "github"
                   / distribution_relative(TEMPLATE_PATHS[key]), content)

    # --- 1 + 2: pre-existing user templates survive install --------------

    def test_pre_existing_issue_template_survives_install(self) -> None:
        self.user_writes(TEMPLATE_PATHS["bug"], BUG_USER)
        result = self.install("standard")
        actions = {change.path: change.action for change in self.template_changes(result)}
        self.assertEqual(actions[TEMPLATE_PATHS["bug"]], "CONFLICT")
        self.assertEqual(self.read(TEMPLATE_PATHS["bug"]), BUG_USER)
        self.assertNotIn(TEMPLATE_PATHS["bug"], self.tracked_template_paths())
        self.assertTrue(any("left untouched" in notice for notice in result.notices),
                        f"the user must be told: {result.notices}")

    def test_pre_existing_pr_template_survives_install(self) -> None:
        self.user_writes(TEMPLATE_PATHS["pr"], BUG_USER)
        result = self.install("standard")
        actions = {change.path: change.action for change in self.template_changes(result)}
        self.assertEqual(actions[TEMPLATE_PATHS["pr"]], "CONFLICT")
        self.assertEqual(self.read(TEMPLATE_PATHS["pr"]), BUG_USER)
        self.assertNotIn(TEMPLATE_PATHS["pr"], self.tracked_template_paths())

    # --- 3: idempotence ---------------------------------------------------

    def test_managed_template_install_is_idempotent(self) -> None:
        self.seeded()
        again = self.install("standard")
        # SKIP is recorded, not silent: the plan must show it stepped around
        # every template while mutating nothing.
        self.assertEqual([change.action for change in self.template_changes(again)],
                         ["SKIP", "SKIP", "SKIP"])
        self.assertTrue(again.plan.is_noop,
                        f"second install mutated: {again.plan.counts()}")

    # --- 4: unchanged managed templates are updatable ---------------------

    def test_unchanged_managed_template_is_updated_when_distribution_changes(self) -> None:
        self.seeded()
        self.distribution_sets("bug", BUG_V2)
        result = self.install("standard")
        actions = {change.path: change.action for change in self.template_changes(result)}
        self.assertEqual(actions[TEMPLATE_PATHS["bug"]], "REPLACE")
        self.assertEqual(self.read(TEMPLATE_PATHS["bug"]), BUG_V2)

    # --- 5: user-modified managed templates are preserved and reported ----

    def test_user_modified_managed_template_is_preserved_and_reported(self) -> None:
        self.seeded()
        self.user_writes(TEMPLATE_PATHS["bug"], BUG_USER)
        self.distribution_sets("bug", BUG_V2)
        result = self.install("standard")
        actions = {change.path: change.action for change in self.template_changes(result)}
        self.assertEqual(actions[TEMPLATE_PATHS["bug"]], "CONFLICT")
        self.assertEqual(self.read(TEMPLATE_PATHS["bug"]), BUG_USER)
        self.assertTrue(any("left untouched" in notice for notice in result.notices),
                        f"the user must be told: {result.notices}")

    # --- 6: uninstall never deletes user-owned templates ------------------

    def test_uninstall_preserves_user_modified_template(self) -> None:
        self.seeded()
        self.user_writes(TEMPLATE_PATHS["bug"], BUG_USER)
        self.uninstall()
        self.assertEqual(self.read(TEMPLATE_PATHS["bug"]), BUG_USER)

    def test_uninstall_preserves_pre_existing_template(self) -> None:
        self.user_writes(TEMPLATE_PATHS["feature"], BUG_USER)
        self.seeded()
        self.uninstall()
        self.assertEqual(self.read(TEMPLATE_PATHS["feature"]), BUG_USER)

    def test_uninstall_removes_unchanged_managed_template(self) -> None:
        # The counterpart the ownership model guarantees: a template the stack
        # wrote and the user never touched is the stack's to take back.
        self.seeded()
        self.uninstall()
        self.assertFalse(self.exists(TEMPLATE_PATHS["pr"]))

    # --- 7: --dry-run performs no filesystem mutation ----------------------

    def test_dry_run_performs_no_filesystem_mutation(self) -> None:
        self.user_writes(TEMPLATE_PATHS["bug"], BUG_USER)
        before = self.read(TEMPLATE_PATHS["bug"])
        result = self.install("standard", dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertTrue(result.plan.mutating, "the dry run must still show what would happen")
        self.assertEqual(self.read(TEMPLATE_PATHS["bug"]), before)
        self.assertFalse(self.exists(TEMPLATE_PATHS["feature"]))
        self.assertFalse(self.exists(TEMPLATE_PATHS["pr"]))
        self.assertFalse(self.exists(".ai-native/lifecycle/state.json"))

    # --- the directory itself is never claimed -----------------------------

    def test_user_files_elsewhere_in_github_are_untouched_and_untracked(self) -> None:
        self.user_writes(".github/workflows/user-ci.yml", "on: push\n")
        self.seeded()
        self.assertEqual(self.read(".github/workflows/user-ci.yml"), "on: push\n")
        self.assertNotIn(".github/workflows/user-ci.yml", self.tracked_template_paths())
        self.uninstall()
        self.assertEqual(self.read(".github/workflows/user-ci.yml"), "on: push\n")


if __name__ == "__main__":
    sys.exit(__import__("unittest").main())