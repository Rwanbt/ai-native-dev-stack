#!/usr/bin/env python3
"""One gate for one fact: every version label of a release must agree.

`VERSION`, `ainative.__version__` and the package metadata were already tied
together by the build (see `_payload_staging.py`). What remained open was the
release identity: a tag `v2.2.2` could promote a tree whose `VERSION` said
2.2.1, and the published bundle would then carry an internal VERSION no
consumer compared against the release it came from (AUD-201). This gate closes
the chain:

    TAG_VERSION
    == ROOT_VERSION (VERSION)
    == PACKAGE_VERSION (ainative.__version__)
    == WHEEL_VERSION (filename and METADATA, with --dist)
    == SDIST_VERSION (filename and PKG-INFO, with --dist)
    == BUNDLE_VERSION (filename and internal VERSION, with --dist)

The release workflow runs it before publishing and again over the built
artifacts; a maintainer can run it before tagging. It exits non-zero with the
disagreeing labels named, and never "fixes" anything.

Usage:
    python scripts/check_release_versions.py
    python scripts/check_release_versions.py --tag v2.2.2
    python scripts/check_release_versions.py --tag v2.2.2 --dist dist
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from _payload_staging import assert_version_consistency  # noqa: E402
from ainative.lifecycle.provider import lifecycle_bundle_name  # noqa: E402

_STACK_VERSION = re.compile(r"stack-version:\s*([0-9][0-9A-Za-z.\-]*)")


class ReleaseVersionMismatch(RuntimeError):
    """Two labels of the same release disagree."""


def agents_stack_version(root: Path) -> str:
    match = _STACK_VERSION.search((root / "AGENTS.md").read_text(encoding="utf-8"))
    if match is None:
        raise ReleaseVersionMismatch("AGENTS.md lost its stack-version header")
    return match.group(1)


def check_labels(root: Path, tag: str | None = None) -> str:
    """VERSION == ainative.__version__ == AGENTS.md, and (when given) the tag."""

    version = assert_version_consistency(root)
    declared = agents_stack_version(root)
    if declared != version:
        raise ReleaseVersionMismatch(
            f"AGENTS.md declares stack-version {declared!r} but VERSION says {version!r}")
    if tag is not None and tag != f"v{version}":
        raise ReleaseVersionMismatch(
            f"tag {tag!r} does not name the VERSION file ({version!r}); "
            f"expected {f'v{version}'!r}")
    return version


def _metadata_version(payload: bytes) -> str | None:
    for line in payload.decode("utf-8", "replace").splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


def check_dist(version: str, dist: Path) -> list[str]:
    """Each built artifact must be named for, and declare, `version`."""

    if not dist.is_dir():
        raise ReleaseVersionMismatch(f"no dist directory at {dist}")
    checked: list[str] = []

    bundle_name = lifecycle_bundle_name(version)
    bundle = dist / bundle_name
    if not bundle.is_file():
        raise ReleaseVersionMismatch(
            f"lifecycle bundle {bundle_name!r} is missing from {dist}")
    with zipfile.ZipFile(bundle) as archive:
        internal = archive.read("VERSION").decode("utf-8").strip()
    if internal != version:
        raise ReleaseVersionMismatch(
            f"lifecycle bundle {bundle_name!r} contains VERSION {internal!r}")
    checked.append(bundle_name)

    wheels = sorted(dist.glob(f"ainative_dev_stack-{version}-*.whl"))
    if not wheels:
        raise ReleaseVersionMismatch(
            f"no wheel built for {version} in {dist} (expected ainative_dev_stack-{version}-*.whl)")
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            metadata = next((entry for entry in archive.namelist()
                             if entry.endswith(".dist-info/METADATA")), None)
            if metadata is None:
                raise ReleaseVersionMismatch(f"{wheel.name} carries no METADATA")
            built = _metadata_version(archive.read(metadata))
        if built != version:
            raise ReleaseVersionMismatch(
                f"wheel {wheel.name!r} declares metadata version {built!r}")
        checked.append(wheel.name)

    sdists = sorted(dist.glob(f"ainative_dev_stack-{version}.tar.gz"))
    if not sdists:
        raise ReleaseVersionMismatch(
            f"no sdist built for {version} in {dist} (expected ainative_dev_stack-{version}.tar.gz)")
    for sdist in sdists:
        with tarfile.open(sdist, "r:gz") as archive:
            pkg_info = next((entry for entry in archive.getmembers()
                             if entry.name.endswith("/PKG-INFO")), None)
            if pkg_info is None:
                raise ReleaseVersionMismatch(f"{sdist.name} carries no PKG-INFO")
            extracted = archive.extractfile(pkg_info)
            built = _metadata_version(extracted.read()) if extracted else None
        if built != version:
            raise ReleaseVersionMismatch(
                f"sdist {sdist.name!r} declares metadata version {built!r}")
        checked.append(sdist.name)

    # An artifact from another version in the same dist tree would be published
    # beside this release and confuse every consumer that guesses by glob.
    stale = sorted(
        item.name for item in dist.iterdir()
        if item.is_file() and item.name not in checked
        and re.search(r"ainative[_-]dev[_-]stack[-_]", item.name)
        and re.search(r"\d+\.\d+\.\d+", item.name))
    if stale:
        raise ReleaseVersionMismatch(
            f"artifacts for another version are present in {dist}: {stale}")
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--tag", default=None,
                        help="the release tag being published, e.g. v2.2.2")
    parser.add_argument("--dist", type=Path, default=None,
                        help="also verify the built artifacts in this directory")
    args = parser.parse_args()

    try:
        version = check_labels(args.root, args.tag)
        artifacts = check_dist(version, args.dist) if args.dist else []
    except ReleaseVersionMismatch as refusal:
        print(f"RELEASE_VERSION_MISMATCH: {refusal}", file=sys.stderr)
        return 1

    print(f"release version {version}: labels agree"
          + (f"; artifacts verified: {', '.join(artifacts)}" if artifacts else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
