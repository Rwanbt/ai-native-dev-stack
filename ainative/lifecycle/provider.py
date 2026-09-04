"""Where a release comes from.

Two implementations and one interface, because the tests must exercise the whole
update path — check, download, digest verification, extraction, conflict,
rollback — without reaching the network, and because a user must be able to
point the updater at an internal mirror.

This is not a plugin system. There is no registry, no discovery, no entry
points: two classes and a factory that reads one environment variable.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import version as versionlib
from .digest import digest_bytes
from .errors import LifecycleError

DEFAULT_RELEASE_URL = "https://api.github.com/repos/Rwanbt/ai-native-dev-stack/releases/latest"
PROVIDER_ENV = "AINATIVE_UPDATE_PROVIDER"     # "github" (default) | "local"
LOCAL_SOURCE_ENV = "AINATIVE_UPDATE_LOCAL_DIR"
RELEASE_URL_ENV = "AINATIVE_UPDATE_URL"

# Short on purpose: an update check runs in the background of a status command,
# and a user must never wait on a slow endpoint to be told their profile.
NETWORK_TIMEOUT_SECONDS = 5
MAX_METADATA_BYTES = 1 << 20      # 1 MiB of release JSON is already absurd
MAX_ARCHIVE_BYTES = 256 << 20     # 256 MiB


@dataclass(frozen=True)
class Release:
    version: str
    url: str | None
    digest: str | None       # sha256 of the archive, when the source publishes one
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

    The index names the channel, the version and the archive digest, exactly as
    a remote source would, so a test exercises the same code path a user does.
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
        archive = entry.get("archive")
        url = str((self.root / archive).resolve()) if archive else None
        return Release(version=str(entry["version"]), url=url,
                       digest=entry.get("sha256"), notes=str(entry.get("notes", "")),
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
    """The official source: a JSON release document naming a versioned archive.

    Everything read here is attacker-influenceable in the sense that matters:
    it arrives over the network. So the size is bounded before it is parsed, the
    version must be SemVer, and the archive URL must be HTTPS.
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
        url, sha = _select_asset(document)
        return Release(version=str(parsed), url=url, digest=sha,
                       notes=str(document.get("body", ""))[:2000], source=self.url)

    def fetch(self, release: Release) -> bytes:
        if not release.url:
            raise LifecycleError("UPDATE_UNAVAILABLE", "release declares no archive")
        return self._get(release.url, MAX_ARCHIVE_BYTES)


def _select_asset(document: dict) -> tuple[str | None, str | None]:
    """Pick the `.zip` asset and its published digest, if the source gives one."""

    assets = document.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name", ""))
            url = asset.get("browser_download_url")
            if name.endswith(".zip") and isinstance(url, str):
                digest = asset.get("digest")
                sha = None
                if isinstance(digest, str) and digest.startswith("sha256:"):
                    sha = digest.split(":", 1)[1]
                return url, sha
    zipball = document.get("zipball_url")
    return (zipball if isinstance(zipball, str) else None), None


def verify_archive(payload: bytes, expected: str | None) -> str:
    """Return the archive's digest, refusing a mismatch.

    SHA-256 here proves the bytes are the bytes the source described. It does
    not prove the source is honest; see ADR-0009 §6 and the threat model.
    """

    actual = digest_bytes(payload)
    if expected and actual.lower() != expected.lower():
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
    "build", "verify_archive", "copy_tree",
    "PROVIDER_ENV", "LOCAL_SOURCE_ENV", "RELEASE_URL_ENV", "DEFAULT_RELEASE_URL",
    "NETWORK_TIMEOUT_SECONDS", "MAX_ARCHIVE_BYTES", "MAX_METADATA_BYTES",
]
