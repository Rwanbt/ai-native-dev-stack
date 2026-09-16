"""EN/FR documentation parity, stated structurally (plan section 75).

Raw line counts are not parity: a translation legitimately differs in length.
What must agree is structure — the heading hierarchy of the README pair — and
what must appear in both is the *operational surface* a user types: command
names, environment variables and configuration file names. A translated page
that silently drops a command or a security section fails here.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGLISH = REPO / "README.md"
FRENCH = REPO / "README.fr.md"

FENCE = "```"

# The operational surface introduced by Multi-Forge: present in both languages
# or the translation has fallen behind the tool.
OPERATIONAL_KEYS = (
    "ainative feature status",
    "ainative feature switch forge-gitlab",
    "ainative feature switch none",
    "ainative forge status",
    "ainative claim-attempt list",
    "AINATIVE_UPDATE_URL",
    "release-providers.json",
    "FORGE-WORKFLOW.md",
    "SUPPORT.md",
)


def heading_levels(text: str) -> list[int]:
    """Heading levels outside fenced code blocks, in document order."""

    levels: list[int] = []
    fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(FENCE):
            fence = not fence
            continue
        if fence:
            continue
        if stripped.startswith("#"):
            levels.append(len(stripped) - len(stripped.lstrip("#")))
    return levels


class DocumentationParity(unittest.TestCase):

    def setUp(self) -> None:
        self.english = ENGLISH.read_text(encoding="utf-8")
        self.french = FRENCH.read_text(encoding="utf-8")

    def test_the_heading_hierarchy_is_identical_between_languages(self):
        self.assertEqual(heading_levels(self.english), heading_levels(self.french),
                         "the EN/FR README structures drifted apart")

    def test_both_languages_speak_the_operational_surface(self):
        for key in OPERATIONAL_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, self.english)
                self.assertIn(key, self.french)

    def test_the_critical_security_statements_appear_in_both(self):
        # The statements, not the words: the French page says "ancré".
        self.assertIn("fail-closed", self.english)
        self.assertIn("anchored", self.english)
        self.assertIn("fail-closed", self.french)
        self.assertIn("ancré", self.french)


if __name__ == "__main__":
    unittest.main()
