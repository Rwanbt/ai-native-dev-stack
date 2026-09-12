"""In-tree PEP 517 backend: stage the distribution payload into the package.

The lifecycle installer copies real files — skills, `tools/ai_docs`, `AGENTS.md`
— into a user's project. Those files live once in this repository, which is the
right place for them: duplicating them under `ainative/` would give the stack two
copies of its own method to keep in sync.

But a user who runs `pip install` on a machine with no checkout has only the
wheel. So the payload is *materialised at build time* instead of being tracked
twice: this backend copies the authoritative files into `ainative/_payload/`
just before setuptools builds, and `ainative/lifecycle/source.py` reads them
from there when no checkout is present.

`ainative/_payload/` is generated and git-ignored. Editing it has no effect —
edit the source of truth at the repository root.

Staging and the version-consistency gate live in `_payload_staging.py` so the
release bundle script and this backend share one implementation.
"""

from __future__ import annotations

from pathlib import Path

from setuptools import build_meta as _setuptools

from _payload_staging import assert_version_consistency, stage_payload as _stage

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "ainative" / "_payload"


def stage_payload() -> Path:
    """Refresh `ainative/_payload/`, refusing a two-version distribution.

    A wheel is the one place a user cannot see that `VERSION` and
    `ainative.__version__` disagree; v2.2.0 shipped exactly that (#125), so the
    build now fails closed instead of producing the artifact.
    """

    assert_version_consistency(ROOT)
    return _stage(ROOT, PAYLOAD)


# --- PEP 517 hooks: stage, then delegate ---------------------------------


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    stage_payload()
    return _setuptools.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(sdist_directory, config_settings=None):
    stage_payload()
    return _setuptools.build_sdist(sdist_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    # An editable install runs from the checkout, which `source.py` prefers
    # anyway; staging keeps the two paths identical rather than only one tested.
    stage_payload()
    return _setuptools.build_editable(wheel_directory, config_settings, metadata_directory)


get_requires_for_build_wheel = _setuptools.get_requires_for_build_wheel
get_requires_for_build_sdist = _setuptools.get_requires_for_build_sdist
get_requires_for_build_editable = _setuptools.get_requires_for_build_editable
prepare_metadata_for_build_wheel = _setuptools.prepare_metadata_for_build_wheel
prepare_metadata_for_build_editable = _setuptools.prepare_metadata_for_build_editable