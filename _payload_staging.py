"""Stage the distribution payload, and gate version consistency at build time.

Single owner for two facts that used to live in two places:

* what a project install needs (``PAYLOAD_TREES``, ``PAYLOAD_FILES``);
* what version the distribution declares.

``VERSION``, ``ainative/__init__.py`` and the package metadata are three
representations of one fact. The packaged metadata derives from
``ainative.__version__`` (pyproject ``attr``), and the lifecycle reads
``VERSION``; nothing enforced that the two agreed, so the v2.2.0 wheel shipped
with ``VERSION = 2.0.0`` beside a 2.2.0 package (#125). Every build entry
point now refuses to produce an artifact whose two labels disagree.

Stdlib-only on purpose: the PEP 517 backend imports this module inside build
environments where nothing else is installed, and the release-bundle script
uses the same staging.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

PAYLOAD_DIRNAME = Path("ainative") / "_payload"

# What a project install needs, and nothing more. The wheel does not carry the
# test suite, the docs archive or the anti-debt agent.
PAYLOAD_TREES = ("skills", "tools/ai_docs", "templates")
PAYLOAD_FILES = ("AGENTS.md", "VERSION", "conventions.json",
                 "docs/VERIFIED-WORK-PLANE.md")

# Only build noise. A skill's own `tests/` directory is part of the skill, so
# pruning it here would make a wheel install differ from a checkout install —
# the one thing the payload exists to prevent.
EXCLUDED = {"__pycache__", ".pytest_cache"}


class VersionMismatch(RuntimeError):
    """The distribution's two version labels disagree; the build is refused."""


def read_version(root: Path) -> str:
    """The ``VERSION`` file: the label the lifecycle records on install."""

    return (root / "VERSION").read_text(encoding="utf-8").strip()


def package_version(root: Path) -> str:
    """``ainative.__version__``, read statically (no import, no side effects)."""

    module = ast.parse((root / "ainative" / "__init__.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            raise VersionMismatch("ainative.__version__ is not a string literal")
    raise VersionMismatch("ainative/__init__.py declares no __version__")


def assert_version_consistency(root: Path) -> str:
    """Refuse a build whose two version labels disagree, and return the version."""

    declared = read_version(root)
    packaged = package_version(root)
    if declared != packaged:
        raise VersionMismatch(
            f"VERSION says {declared!r} but ainative.__version__ says {packaged!r}; "
            "one distribution must not carry two versions")
    return declared


def stage_payload(root: Path, destination: Path) -> Path:
    """Materialise a payload tree from the authoritative sources at ``root``."""

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for relative in PAYLOAD_TREES:
        source = root / relative
        if source.is_dir():
            shutil.copytree(source, destination / relative, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(*EXCLUDED, "*.pyc", "config.sh"))
    for relative in PAYLOAD_FILES:
        source = root / relative
        if source.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (destination / "PAYLOAD.md").write_text(
        "Generated at build time. Do not edit: the sources of truth are at the "
        "repository root.\n", encoding="utf-8")
    return destination


__all__ = ["PAYLOAD_DIRNAME", "PAYLOAD_TREES", "PAYLOAD_FILES", "EXCLUDED",
           "VersionMismatch", "read_version", "package_version",
           "assert_version_consistency", "stage_payload"]