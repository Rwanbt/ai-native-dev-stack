"""Neutral modules must not depend on provider implementations (ADR-0019 §74).

`ainative.forge`, `ainative.claims` and `ainative.cli_support` are the neutral
layer: provider-neutral facts, identities and plumbing. They may import the
lifecycle's errors and state (neutral infrastructure), never a provider
implementation, the release transport, the updater or the observation module —
a neutral module that reaches a provider is a coupling that makes the neutral
layer untestable without a network or a forge.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

NEUTRAL_MODULES = ("ainative/forge.py", "ainative/claims.py", "ainative/cli_support.py")
BANNED_PREFIXES = (
    "ainative.lifecycle.provider",
    "ainative.lifecycle.release_providers",
    "ainative.lifecycle.transport",
    "ainative.lifecycle.updater",
    "ainative.lifecycle.release_source",
    "ainative.observation",
)


def imported_modules(path: Path) -> set[str]:
    """Every module name `path` imports, with relative imports resolved."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = "ainative" if path.parent.name == "ainative" \
                    else "ainative.lifecycle"
                found.add(f"{package}.{node.module}" if node.module else package)
            elif node.module:
                found.add(node.module)
    return found


class DependencyPurity(unittest.TestCase):

    def test_neutral_modules_never_import_a_provider_or_the_transport(self):
        for relative in NEUTRAL_MODULES:
            with self.subTest(module=relative):
                imports = imported_modules(REPO / relative)
                offenders = {name for name in imports
                             if any(name == banned or name.startswith(banned + ".")
                                    for banned in BANNED_PREFIXES)}
                self.assertEqual(offenders, set(), relative)


if __name__ == "__main__":
    unittest.main()
