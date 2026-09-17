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
    == WHEEL_VERSION (filename and METADATA)
    == SDIST_VERSION (filename and PKG-INFO)
    == BUNDLE_VERSION (filename, protocol document, payload VERSION)

The release workflow runs it before publishing and again over the built
artifacts; the PyPI workflow runs the wheel/sdist half with --without-bundle
(PyPI ships no lifecycle bundle); a maintainer can run it before tagging. It
exits non-zero with the disagreeing labels named, and never "fixes" anything.

Usage:
    python scripts/check_release_versions.py
    python scripts/check_release_versions.py --tag v2.2.2
    python scripts/check_release_versions.py --tag v2.2.2 --dist dist
    python scripts/check_release_versions.py --tag v2.2.2 --dist dist --without-bundle
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from _payload_staging import assert_version_consistency  # noqa: E402
from ainative.lifecycle import release_v3 as release_v3lib  # noqa: E402
from ainative.lifecycle.errors import LifecycleError  # noqa: E402
from ainative.lifecycle.provider import (PROTOCOL_MANIFEST,  # noqa: E402
                                         UPDATE_PROTOCOL_VERSION,
                                         lifecycle_bundle_name)

_STACK_VERSION = re.compile(r"stack-version:\s*([0-9][0-9A-Za-z.\-]*)")
_ARTIFACT = re.compile(r"ainative[_-](?:dev[_-]stack|lifecycle[_-]v\d+)[-_]")
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


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


def _stale_artifacts(dist: Path, checked: set[str], version: str) -> list[str]:
    """Files that name another version would be published beside this release."""

    stale: list[str] = []
    for item in sorted(dist.iterdir()):
        if not item.is_file() or item.name in checked:
            continue
        if _ARTIFACT.search(item.name) and _SEMVER.search(item.name) \
                and version not in item.name:
            stale.append(item.name)
    return stale


def _check_bundle(version: str, dist: Path, checked: set[str]) -> None:
    bundle_name = lifecycle_bundle_name(version)
    bundle = dist / bundle_name
    if not bundle.is_file():
        raise ReleaseVersionMismatch(
            f"lifecycle bundle {bundle_name!r} is missing from {dist}")
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        if PROTOCOL_MANIFEST not in names:
            raise ReleaseVersionMismatch(
                f"lifecycle bundle {bundle_name!r} carries no {PROTOCOL_MANIFEST}")
        document = json.loads(archive.read(PROTOCOL_MANIFEST).decode("utf-8"))
        if document.get("protocol_version") != UPDATE_PROTOCOL_VERSION:
            raise ReleaseVersionMismatch(
                f"lifecycle bundle {bundle_name!r} declares protocol "
                f"{document.get('protocol_version')!r}")
        if document.get("release_version") != version:
            raise ReleaseVersionMismatch(
                f"lifecycle bundle {bundle_name!r} declares release_version "
                f"{document.get('release_version')!r}")
        payload_root = str(document.get("payload_root", ""))
        payload_version = archive.read(f"{payload_root}/VERSION").decode("utf-8").strip()
    if payload_version != version:
        raise ReleaseVersionMismatch(
            f"lifecycle bundle {bundle_name!r} contains VERSION {payload_version!r}")
    checked.add(bundle_name)


def detect_protocol(dist: Path) -> int | None:
    """The lifecycle protocol this dist carries, from the artifacts themselves."""

    names = {item.name for item in dist.iterdir() if item.is_file()}
    has_v3 = release_v3lib.MANIFEST_ASSET_NAME in names or any(
        name.startswith("ainative-lifecycle-v3-") and name.endswith(".zip")
        for name in names)
    has_v2 = any(name.startswith("ainative-lifecycle-v2-") and name.endswith(".zip")
                 for name in names)
    if has_v3 and has_v2:
        raise ReleaseVersionMismatch(
            "the dist mixes a V2 lifecycle bundle with V3 artifacts; a release "
            "is exactly one protocol")
    if has_v3:
        return release_v3lib.BUNDLE_PROTOCOL_VERSION
    if has_v2:
        return UPDATE_PROTOCOL_VERSION
    return None


def _check_v3(version: str, dist: Path, checked: set[str]) -> None:
    """The V3 chain: manifest, exact version links, anchored artifact bytes."""

    manifest_path = dist / release_v3lib.MANIFEST_ASSET_NAME
    if not manifest_path.is_file():
        raise ReleaseVersionMismatch(
            f"the V3 manifest {release_v3lib.MANIFEST_ASSET_NAME!r} is missing "
            f"from {dist}")
    try:
        manifest = release_v3lib.parse_manifest(manifest_path.read_bytes())
        artifact = manifest.lifecycle_artifact()
        candidate = release_v3lib.ReleaseCandidate(
            version=manifest.version, identity=manifest.version)
        release_v3lib.require_exact_version_chain(candidate, manifest, artifact)
    except LifecycleError as refusal:
        raise ReleaseVersionMismatch(
            f"the V3 manifest is invalid: {refusal.code}: {refusal.message}") from refusal
    if manifest.version != version:
        raise ReleaseVersionMismatch(
            f"the V3 manifest declares version {manifest.version!r} but the "
            f"release is {version!r}")
    if manifest.runtime_version != version:
        raise ReleaseVersionMismatch(
            f"the V3 manifest requires runtime {manifest.runtime_version!r} but "
            f"the release is {version!r}")
    bundle = dist / artifact.name
    if not bundle.is_file():
        raise ReleaseVersionMismatch(
            f"the lifecycle artifact {artifact.name!r} is missing from {dist}")
    payload = bundle.read_bytes()
    actual_digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != artifact.size or actual_digest != artifact.sha256:
        raise ReleaseVersionMismatch(
            f"the lifecycle artifact {artifact.name!r} does not match the "
            f"manifest (size {len(payload)} vs {artifact.size}, sha256 "
            f"{actual_digest} vs {artifact.sha256})")
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        if PROTOCOL_MANIFEST not in names:
            raise ReleaseVersionMismatch(
                f"lifecycle bundle {artifact.name!r} carries no {PROTOCOL_MANIFEST}")
        document = json.loads(archive.read(PROTOCOL_MANIFEST).decode("utf-8"))
        if document.get("protocol_version") != release_v3lib.BUNDLE_PROTOCOL_VERSION:
            raise ReleaseVersionMismatch(
                f"lifecycle bundle {artifact.name!r} declares protocol "
                f"{document.get('protocol_version')!r}, expected "
                f"{release_v3lib.BUNDLE_PROTOCOL_VERSION}")
        if document.get("release_version") != version:
            raise ReleaseVersionMismatch(
                f"lifecycle bundle {artifact.name!r} declares release_version "
                f"{document.get('release_version')!r}")
        payload_root = str(document.get("payload_root", ""))
        payload_version = archive.read(f"{payload_root}/VERSION").decode("utf-8").strip()
    if payload_version != version:
        raise ReleaseVersionMismatch(
            f"lifecycle bundle {artifact.name!r} contains VERSION {payload_version!r}")
    checked.add(manifest_path.name)
    checked.add(artifact.name)


def _check_wheel(version: str, dist: Path, checked: set[str]) -> None:
    wheels = sorted(dist.glob(f"ainative_dev_stack-{version}-*.whl"))
    if not wheels:
        raise ReleaseVersionMismatch(
            f"no wheel built for {version} in {dist} "
            f"(expected ainative_dev_stack-{version}-*.whl)")
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
        checked.add(wheel.name)


def _check_sdist(version: str, dist: Path, checked: set[str]) -> None:
    sdists = sorted(dist.glob(f"ainative_dev_stack-{version}.tar.gz"))
    if not sdists:
        raise ReleaseVersionMismatch(
            f"no sdist built for {version} in {dist} "
            f"(expected ainative_dev_stack-{version}.tar.gz)")
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
        checked.add(sdist.name)


def check_dist(version: str, dist: Path, *, require_bundle: bool = True,
               protocol: int | None = None) -> list[str]:
    """Each built artifact must be named for, and declare, `version`.

    The lifecycle protocol is detected from the artifacts themselves (a V3
    manifest or V3 bundle means protocol 3; a V2 bundle means protocol 2; both
    together are refused), unless `protocol` states the expectation.
    `require_bundle=False` is the PyPI path: PyPI ships the wheel and the
    sdist, not the lifecycle bundle, which GitHub Releases carries.
    """

    if not dist.is_dir():
        raise ReleaseVersionMismatch(f"no dist directory at {dist}")
    checked: set[str] = set()
    if require_bundle:
        actual = detect_protocol(dist)
        if protocol is not None and actual is not None and actual != protocol:
            raise ReleaseVersionMismatch(
                f"the dist carries lifecycle protocol {actual} but protocol "
                f"{protocol} was expected")
        expected = protocol if protocol is not None else actual
        if expected == release_v3lib.BUNDLE_PROTOCOL_VERSION:
            _check_v3(version, dist, checked)
        else:
            _check_bundle(version, dist, checked)
    _check_wheel(version, dist, checked)
    _check_sdist(version, dist, checked)
    stale = _stale_artifacts(dist, checked, version)
    if stale:
        raise ReleaseVersionMismatch(
            f"artifacts for another version are present in {dist}: {stale}")
    return sorted(checked)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--tag", default=None,
                        help="the release tag being published, e.g. v2.2.2")
    parser.add_argument("--dist", type=Path, default=None,
                        help="also verify the built artifacts in this directory")
    parser.add_argument("--protocol", type=int, choices=(2, 3), default=None,
                        help="the lifecycle protocol to expect; default: from the dist")
    parser.add_argument("--without-bundle", action="store_true",
                        help="check only the wheel and the sdist (the PyPI surface)")
    args = parser.parse_args()

    try:
        version = check_labels(args.root, args.tag)
        artifacts = (check_dist(version, args.dist,
                                require_bundle=not args.without_bundle,
                                protocol=args.protocol)
                     if args.dist else [])
    except ReleaseVersionMismatch as refusal:
        print(f"RELEASE_VERSION_MISMATCH: {refusal}", file=sys.stderr)
        return 1

    print(f"release version {version}: labels agree"
          + (f"; artifacts verified: {', '.join(artifacts)}" if artifacts else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())