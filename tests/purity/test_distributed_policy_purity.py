"""The distributed policy speaks provider-neutral Work Authority (§74).

`templates/AGENTS.md` is what every project receives; the repository's own
`AGENTS.md` may stay GitHub-specific. The distributed file may name the
mappings, but it must not carry GitHub-only *authority*: no GitHub-only claim
procedure, no GitHub-only credential, no GitHub-only canonical-backlog
statement.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DISTRIBUTED = REPO / "templates" / "AGENTS.md"

FORBIDDEN_AUTHORITY = (
    "GitHub Issues are the canonical actionable backlog",
    "docs/GITHUB-WORKFLOW.md",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


class DistributedPolicyPurity(unittest.TestCase):

    def setUp(self) -> None:
        self.text = DISTRIBUTED.read_text(encoding="utf-8")

    def test_no_github_only_authority_survives_in_the_distributed_policy(self):
        for phrase in FORBIDDEN_AUTHORITY:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.text)

    def test_the_distributed_policy_names_the_neutral_rules(self):
        self.assertIn("Work Authority", self.text)
        self.assertIn("WorkItem", self.text)
        self.assertIn("FORGE-WORKFLOW.md", self.text)
        self.assertIn("ainative claim-attempt", self.text)
        self.assertIn("ACTIVE_PR_CONFLICT", self.text)

    def test_the_repository_own_policy_may_stay_github_specific(self):
        own = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("GitHub work management", own)


if __name__ == "__main__":
    unittest.main()
