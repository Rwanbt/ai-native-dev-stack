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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import transport as transportlib
from . import version as versionlib
from .digest import digest_bytes
from .errors import LifecycleError
# The selector names live with their owner (release_source); re-exported here
# because they have always been importable through the provider module.
from .release_source import LOCAL_SOURCE_ENV, PROVIDER_ENV, RELEASE_URL_ENV


def _update_token() -> str:
    """The token this environment offers, if any. Never logged anywhere."""

    for name in TOKEN_ENVS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def environment_token() -> str:
    """The token this environment offers, if any. Never logged anywhere.

    Public for the V3 providers, which attach it only when the transport's
    endpoint rule allows the origin (PR-0A).
    """

    return _update_token()

DEFAULT_RELEASE_URL = "https://api.github.com/repos/Rwanbt/ai-native-dev-stack/releases/latest"
# Authenticated checks, when the environment provides a token. Never logged,
# never persisted: NAT-shared users hit the anonymous rate limit otherwise.
TOKEN_ENVS = ("GITHUB_TOKEN", "GH_TOKEN")

# The update protocol. v1 (runtimes <= 2.2.2) selected any
# `ainative-dev-stack-*.zip`; v2 names its bundle `ainative-lifecycle-v2-*` and
# wraps the payload so a v1 runtime cannot consume it even through a mirror
# that names the file for it. See docs/DISTRIBUTION-LIFECYCLE.md section 8.
UPDATE_PROTOCOL_VERSION = 2
LIFECYCLE_BUNDLE_PREFIX = "ainative-lifecycle-v2-"
LIFECYCLE_BUNDLE_SUFFIX = ".zip"
PROTOCOL_MANIFEST = "lifecycle-protocol.json"


def lifecycle_bundle_name(version: str) -> str:
    """The one filename this stack accepts for a bundle of `version`."""

    return f"{LIFECYCLE_BUNDLE_PREFIX}{version}{LIFECYCLE_BUNDLE_SUFFIX}"


def protocol_document(version: str) -> dict:
    """The manifest a v2 bundle carries at its root."""

    return {"schema_name": "lifecycle_protocol", "protocol_version": UPDATE_PROTOCOL_VERSION,
            "release_version": version, "payload_root": "stack"}


UPGRADE_COMMAND_TEMPLATE = (
    'pip install --upgrade '
    '"git+https://github.com/Rwanbt/ai-native-dev-stack.git@v{version}"')


def upgrade_command(version: str) -> str:
    """The exact command that installs the runtime a target release needs.

    Lives here rather than in `updater` because a release-source refusal (a
    future lifecycle protocol, #157) must name the upgrade path, and this
    module must not import the updater that consumes it.
    """

    return UPGRADE_COMMAND_TEMPLATE.format(version=version)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Short on purpose: an update check runs in the background of a status command,
# and a user must never wait on a slow endpoint to be told their profile.
NETWORK_TIMEOUT_SECONDS = transportlib.NETWORK_TIMEOUT_SECONDS
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
    version must be SemVer, the bundle's SHA-256 must be published by the source
    — `_select_asset` refuses anything less, which is what makes
    `verify_archive` a comparison rather than a computation — and every request
    goes through `transport.get`, which sends a credential only to the origin
    the endpoint config declares (PR-0A, #158).

    The selector decides which of two endpoints this is:

    * the built-in GitHub.com endpoint — credential origin `api.github.com`, so
      metadata and the asset API are authenticated and a `302` to the CDN is
      followed anonymously;
    * the anonymous endpoint — any URL supplied as the constructor argument or
      through `AINATIVE_UPDATE_URL`. It never receives a credential: its
      metadata may name any artifact URL, and a custom source must not be able
      to obtain the user's provider token by naming one.
    """

    name = "release-api"

    def __init__(self, url: str | None = None, *,
                 endpoint: transportlib.ReleaseProviderEndpointConfig | None = None) -> None:
        if endpoint is not None:
            self.endpoint = endpoint
            self.url = url or endpoint.api_base_url
            return
        override = (url if url is not None
                    else os.environ.get(RELEASE_URL_ENV) or "").strip()
        if override:
            self.endpoint = transportlib.anonymous_endpoint(override)
            self.url = override
        else:
            self.endpoint = transportlib.GITHUB_ENDPOINT
            self.url = DEFAULT_RELEASE_URL

    def _token(self) -> str:
        """The credential this endpoint may use. Anonymous endpoints never do."""

        if self.endpoint.auth_origin is None:
            return ""
        return _update_token()

    def _get(self, url: str, limit: int) -> bytes:
        """Fetch the release document; redirects may not leave its origin."""

        return transportlib.get(url, limit=limit, endpoint=self.endpoint,
                                kind=transportlib.METADATA,
                                accept=transportlib.ACCEPT_GITHUB_JSON,
                                token=self._token())

    def _fetch_artifact(self, url: str, limit: int) -> bytes:
        """Fetch release bytes; a cross-origin redirect is followed anonymously."""

        return transportlib.get(url, limit=limit, endpoint=self.endpoint,
                                kind=transportlib.ARTIFACT,
                                accept=transportlib.ACCEPT_OCTET_STREAM,
                                token=self._token())

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
        return self._fetch_artifact(release.url, MAX_ARCHIVE_BYTES)


def _asset_url(asset: dict) -> str | None:
    """The URL this stack fetches an asset from, or None when it publishes none.

    GitHub serves the asset API URL (`assets[].url`) and, for a private
    repository, a `browser_download_url` that only anonymizes for public
    assets. The API URL is also the only one the transport will authenticate,
    because it lives on the configured API origin; the browser URL stays as the
    fallback so a GitHub-API-compatible mirror that publishes only that field
    keeps working.
    """

    for key in ("url", "browser_download_url"):
        value = asset.get(key)
        if isinstance(value, str) and value.lower().startswith("https://"):
            return value
    return None


# A release that publishes one of these names declares a lifecycle protocol.
# Comparing that number with this runtime's own is what separates "a newer
# release" from "a broken release" (#157): the first must tell the user to
# upgrade the CLI, the second must keep the integrity refusal.
_LIFECYCLE_ASSET_PATTERNS = (
    re.compile(r"^ainative-lifecycle-v(?P<protocol>\d+)-.+\.zip$"),
    re.compile(r"^ainative-release-v(?P<protocol>\d+)\.json$"),
)


def _future_lifecycle_protocol(assets: object) -> int | None:
    """The newest declared lifecycle protocol above this runtime's, or None."""

    newest = None
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", ""))
        for pattern in _LIFECYCLE_ASSET_PATTERNS:
            match = pattern.match(name)
            if match is None:
                continue
            protocol = int(match.group("protocol"))
            if protocol > UPDATE_PROTOCOL_VERSION and (newest is None or protocol > newest):
                newest = protocol
    return newest


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
        if not (name.startswith(LIFECYCLE_BUNDLE_PREFIX)
                and name.endswith(LIFECYCLE_BUNDLE_SUFFIX)):
            continue
        url = _asset_url(asset)
        if url is None:
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
    future = _future_lifecycle_protocol(assets)
    if future is not None:
        raise LifecycleError(
            "CLI_UPDATE_REQUIRED",
            f"release {expected_version} publishes lifecycle protocol {future}; "
            f"this runtime speaks protocol {UPDATE_PROTOCOL_VERSION} and the "
            "release must be applied by a newer CLI runtime.\n\n"
            "Upgrade the CLI first:\n"
            f"  {upgrade_command(expected_version)}\n\n"
            "Then run:\n"
            "  ainative update",
            target_version=expected_version, protocol=future,
            runtime_protocol=UPDATE_PROTOCOL_VERSION,
            upgrade_command=upgrade_command(expected_version))
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
    """The provider this environment selects. One resolver, no discovery.

    The decision lives in `release_source.resolve_release_source()` so
    `update`, `update check`, `status` and `doctor` cannot disagree about it
    (ADR-0019 section 1); this function only constructs the selected provider.
    """

    from . import release_source as release_sourcelib

    source = release_sourcelib.resolve_release_source()
    if source.kind == release_sourcelib.KIND_LOCAL:
        return LocalDirectoryProvider(source.directory)
    return ReleaseApiProvider(url=source.metadata_url, endpoint=source.endpoint)


def copy_tree(source: Path, destination: Path) -> None:
    """Used by the local provider's tests to stage a fixture distribution."""

    shutil.copytree(source, destination, dirs_exist_ok=True)


__all__ = [
    "Release", "UpdateProvider", "LocalDirectoryProvider", "ReleaseApiProvider",
    "build", "verify_archive", "copy_tree", "lifecycle_bundle_name",
    "protocol_document", "UPDATE_PROTOCOL_VERSION", "PROTOCOL_MANIFEST", "TOKEN_ENVS",
    "PROVIDER_ENV", "LOCAL_SOURCE_ENV", "RELEASE_URL_ENV", "DEFAULT_RELEASE_URL",
    "LIFECYCLE_BUNDLE_PREFIX", "LIFECYCLE_BUNDLE_SUFFIX",
    "NETWORK_TIMEOUT_SECONDS", "MAX_ARCHIVE_BYTES", "MAX_METADATA_BYTES",
    "ReleaseProviderEndpointConfig",
    "upgrade_command", "UPGRADE_COMMAND_TEMPLATE", "environment_token",
]