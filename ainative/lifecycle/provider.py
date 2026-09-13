"""Where a release comes from.

Two implementations and one interface, because the tests must exercise the whole
update path — check, download, digest verification, extraction, conflict,
rollback — without reaching the network, and because a user must be able to
point the updater at an internal mirror.

Both providers obey the same integrity contract: a release this stack is
willing to install names exactly one archive AND the SHA-256 of those bytes.
A source that cannot say what it published is refused rather than trusted
(#126). Within a release, the archive's filename must also carry the release's
own version: a bundle whose name says 2.2.1 under a tag that says 2.2.2 is
refused, digest or not (AUD-201). There is no unverified fallback path —
not even the GitHub `zipball_url`, which no digest can ever cover.

This is not a plugin system. There is no registry, no discovery, no entry
points: two classes and a factory that reads one environment variable.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import version as versionlib
from .digest import digest_bytes
from .errors import LifecycleError

DEFAULT_RELEASE_URL = "https://api.github.com/repos/Rwanbt/ai-native-dev-stack/releases/latest"
PROVIDER_ENV = "AINATIVE_UPDATE_PROVIDER"     # "github" (default) | "local"
LOCAL_SOURCE_ENV = "AINATIVE_UPDATE_LOCAL_DIR"
RELEASE_URL_ENV = "AINATIVE_UPDATE_URL"

# The one asset the official update path consumes. Published by
# `scripts/build_lifecycle_bundle.py` beside the wheel and the sdist.
LIFECYCLE_BUNDLE_PREFIX = "ainative-dev-stack-"
LIFECYCLE_BUNDLE_SUFFIX = ".zip"


def lifecycle_bundle_name(version: str) -> str:
    """The one filename this stack accepts for a bundle of `version`."""

    return f"{LIFECYCLE_BUNDLE_PREFIX}{version}{LIFECYCLE_BUNDLE_SUFFIX}"


_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Short on purpose: an update check runs in the background of a status command,
# and a user must never wait on a slow endpoint to be told their profile.
NETWORK_TIMEOUT_SECONDS = 5
MAX_METADATA_BYTES = 1 << 20      # 1 MiB of release JSON is already absurd
MAX_ARCHIVE_BYTES = 256 << 20     # 256 MiB


@dataclass(frozen=True)
class Release:
    version: str
    url: str | None
    digest: str | None       # sha256 of the archive; always present on a selectable release
    notes: str = ""
    source: str = ""

    def to_record(self) -> dict:
        return {"version": self.version, "url": self.url, "sha256": self.digest,
                "source": self.source}


class UpdateProvider:
    """Resolve the latest release, and fetch its archive bytes."""

    name = "abstract"

    def latest(self, channel: str) -> Release:
        raise NotImplementedError

    def fetch(self, release: Release) -> bytes:
        raise NotImplementedError


class LocalDirectoryProvider(UpdateProvider):
    """Releases published as `<dir>/<version>/` plus a `releases.json` index.

    The index names the channel, the version, the archive and the archive
    digest, exactly as a remote source would, so a test exercises the same code
    path a user does. The mirror contract matches the official one: an entry
    without a valid `sha256` is refused, because an update nobody can verify is
    not one this stack performs.
    """

    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _index(self) -> dict:
        path = self.root / "releases.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"cannot read {path}: {error}") from error
        if not isinstance(payload, dict):
            raise LifecycleError("UPDATE_CHECK_FAILED", f"{path} is not a JSON object")
        return payload

    def latest(self, channel: str) -> Release:
        index = self._index()
        entry = (index.get("channels") or {}).get(channel)
        if not isinstance(entry, dict) or not entry.get("version"):
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"local release index declares no {channel!r} channel")
        version = str(entry["version"])
        digest = entry.get("sha256")
        if not (isinstance(digest, str) and _SHA256.match(digest.strip().lower())):
            raise LifecycleError(
                "UPDATE_INTEGRITY_METADATA_MISSING",
                f"local release index declares no valid sha256 for "
                f"{version}; refusing an update this stack cannot verify")
        archive = entry.get("archive")
        if archive is not None:
            name = PurePosixPath(str(archive)).name
            expected = lifecycle_bundle_name(version)
            if name != expected:
                # Same rule as the official source: a mirror publishing
                # {version: 2.2.2, archive: ainative-dev-stack-2.2.1.zip} is
                # refused rather than applied with a version nobody can name.
                raise LifecycleError(
                    "UPDATE_VERSION_MISMATCH",
                    f"local release index declares version {version} but archive "
                    f"{str(archive)!r}; expected {expected!r}",
                    version=version, published=str(archive), expected=expected)
        url = str((self.root / archive).resolve()) if archive else None
        return Release(version=version, url=url,
                       digest=digest.strip().lower(), notes=str(entry.get("notes", "")),
                       source=f"local:{self.root}")

    def fetch(self, release: Release) -> bytes:
        if not release.url:
            raise LifecycleError("UPDATE_UNAVAILABLE", "release declares no archive")
        path = Path(release.url)
        try:
            size = path.stat().st_size
        except OSError as error:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"release archive missing: {error}") from error
        if size > MAX_ARCHIVE_BYTES:
            raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                                 f"release archive is {size} bytes, over the "
                                 f"{MAX_ARCHIVE_BYTES} limit")
        return path.read_bytes()


class ReleaseApiProvider(UpdateProvider):
    """The official source: a JSON release document naming the lifecycle bundle.

    Everything read here is attacker-influenceable in the sense that matters:
    it arrives over the network. So the size is bounded before it is parsed, the
    version must be SemVer, the archive URL must be HTTPS, and the bundle's
    SHA-256 must be published by the source — `_select_asset` refuses anything
    less, which is what makes `verify_archive` a comparison rather than a
    computation.
    """

    name = "release-api"

    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get(RELEASE_URL_ENV) or DEFAULT_RELEASE_URL

    def _get(self, url: str, limit: int) -> bytes:
        if not url.lower().startswith("https://"):
            raise LifecycleError("UPDATE_CHECK_FAILED", f"refusing a non-HTTPS source: {url}")
        request = urllib.request.Request(url, headers={
            "User-Agent": "ainative-lifecycle", "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                payload = response.read(limit + 1)
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"cannot reach the release source: {error}") from error
        if len(payload) > limit:
            raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                                 f"response from {url} exceeds {limit} bytes")
        return payload

    def latest(self, channel: str) -> Release:
        raw = self._get(self.url, MAX_METADATA_BYTES)
        try:
            document = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"release metadata is not valid JSON: {error}") from error
        if not isinstance(document, dict):
            raise LifecycleError("UPDATE_CHECK_FAILED", "release metadata is not an object")
        tag = str(document.get("tag_name") or document.get("name") or "")
        parsed = versionlib.parse(tag)
        if parsed is None:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"release tag {tag!r} is not a SemVer version")
        if channel == "stable" and parsed.pre:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"latest release {tag} is a pre-release; "
                                 "the stable channel has nothing newer")
        url, sha = _select_asset(document, str(parsed))
        return Release(version=str(parsed), url=url, digest=sha,
                       notes=str(document.get("body", ""))[:2000], source=self.url)

    def fetch(self, release: Release) -> bytes:
        if not release.url:
            raise LifecycleError("UPDATE_UNAVAILABLE", "release declares no archive")
        return self._get(release.url, MAX_ARCHIVE_BYTES)


def _select_asset(document: dict, expected_version: str) -> tuple[str | None, str | None]:
    """Pick the lifecycle bundle of `expected_version` and its digest, or refuse.

    The official path accepts exactly one kind of asset: the lifecycle bundle
    published beside the wheel and the sdist, named after the version the
    release itself declares. A mismatched name is a distinct refusal
    (`UPDATE_VERSION_MISMATCH`), not "no bundle found": the digest may cover
    bytes whose internal VERSION is a different release, which no comparison
    can detect until after extraction - so it never reaches the download. A
    digest is not optional either: an update that cannot verify what it
    downloaded is not an update this stack performs (#126). The `zipball_url`
    fallback this function used to return (with `digest=None`, verifying
    nothing) is gone on purpose: no silent unverified path exists.
    """

    expected = lifecycle_bundle_name(expected_version)
    assets = document.get("assets")
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", ""))
        url = asset.get("browser_download_url")
        if not (name.startswith(LIFECYCLE_BUNDLE_PREFIX)
                and name.endswith(LIFECYCLE_BUNDLE_SUFFIX)
                and isinstance(url, str)):
            continue
        if name != expected:
            raise LifecycleError(
                "UPDATE_VERSION_MISMATCH",
                f"release {expected_version} publishes lifecycle bundle {name!r}; "
                f"expected {expected!r}",
                version=expected_version, published=name, expected=expected)
        digest = asset.get("digest")
        if not (isinstance(digest, str) and digest.startswith("sha256:")):
            raise LifecycleError(
                "UPDATE_INTEGRITY_METADATA_MISSING",
                f"release asset {name!r} publishes no sha256 digest; "
                "refusing an update this stack cannot verify")
        sha = digest.split(":", 1)[1].strip().lower()
        if not _SHA256.match(sha):
            raise LifecycleError(
                "UPDATE_INTEGRITY_METADATA_MISSING",
                f"release asset {name!r} carries a malformed sha256 digest")
        return url, sha
    raise LifecycleError(
        "UPDATE_INTEGRITY_METADATA_MISSING",
        f"release publishes no {LIFECYCLE_BUNDLE_PREFIX}*{LIFECYCLE_BUNDLE_SUFFIX} "
        "lifecycle bundle; the official update path refuses what it cannot verify")


def verify_archive(payload: bytes, expected: str | None) -> str:
    """Return the archive's digest, refusing a mismatch or a missing digest.

    SHA-256 proves the bytes are the bytes the source described. It does not
    prove the source is honest; see ADR-0009 §6 and the threat model. A missing
    expected digest is not a weaker success — it is no verification at all, and
    this function refuses it (#126).
    """

    if not expected:
        raise LifecycleError("UPDATE_INTEGRITY_METADATA_MISSING",
                             "no published digest to verify the archive against; "
                             "refusing the update")
    actual = digest_bytes(payload)
    if actual.lower() != expected.lower():
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"archive digest {actual} does not match the published "
                             f"{expected}; nothing was written",
                             expected=expected, actual=actual)
    return actual


def build(channel: str = "stable") -> UpdateProvider:
    """The provider this environment selects. One variable, no discovery."""

    selected = (os.environ.get(PROVIDER_ENV) or "").strip().lower()
    if selected == "local":
        root = os.environ.get(LOCAL_SOURCE_ENV)
        if not root:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"{PROVIDER_ENV}=local requires {LOCAL_SOURCE_ENV}")
        return LocalDirectoryProvider(Path(root))
    if selected in ("", "github", "release-api"):
        return ReleaseApiProvider()
    raise LifecycleError("UPDATE_CHECK_FAILED", f"unknown update provider {selected!r}")


def copy_tree(source: Path, destination: Path) -> None:
    """Used by the local provider's tests to stage a fixture distribution."""

    shutil.copytree(source, destination, dirs_exist_ok=True)


__all__ = [
    "Release", "UpdateProvider", "LocalDirectoryProvider", "ReleaseApiProvider",
    "build", "verify_archive", "copy_tree", "lifecycle_bundle_name",
    "PROVIDER_ENV", "LOCAL_SOURCE_ENV", "RELEASE_URL_ENV", "DEFAULT_RELEASE_URL",
    "LIFECYCLE_BUNDLE_PREFIX", "LIFECYCLE_BUNDLE_SUFFIX",
    "NETWORK_TIMEOUT_SECONDS", "MAX_ARCHIVE_BYTES", "MAX_METADATA_BYTES",
]