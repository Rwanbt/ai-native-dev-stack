"""The V3 providers: GitHub.com, the anonymous release API, and a local mirror.

Each provider implements the contract in `release_v3` and nothing else: it
enumerates what its source publishes, fetches the manifest bytes, fetches an
artifact. Every trust decision stays in `release_v3` — the provider that
fetched a manifest never decides whether to believe it (ADR-0019 sections 9–11).

GitHub and the anonymous release document share the asset-selection rules of
the V2 path: an `assets[].url` API locator is preferred, `browser_download_url`
is the fallback, and neither is ever authenticated off the endpoint's declared
origin (PR-0A). The local mirror executes the same logical chain as a network
provider — its index supplies the manifest locator, size and SHA-256, and
nothing is trusted because "it is on disk".

Enumeration is bounded. A provider that could not exhaust its listing says so
(`complete=False`), and `release_v3.select_candidate` then refuses rather than
picking the best of what it happened to see.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from . import release_v3 as release_v3lib
from . import transport as transportlib
from . import version as versionlib
from .errors import LifecycleError
from .paths import validate_relative

MANIFEST_ASSET_NAME = release_v3lib.MANIFEST_ASSET_NAME
MAX_MANIFEST_BYTES = 1 << 20      # 1 MiB of release manifest is already absurd
MAX_ARCHIVE_BYTES = 256 << 20     # 256 MiB — mirrors the V2 bound
MAX_ENUMERATION_ENTRIES = 30      # one API page; beyond it, incomplete
GITLAB_PACKAGE_NAME = "ai-native-dev-stack"


def _json_object(payload: bytes, source: str) -> dict:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"release metadata from {source} is not valid JSON: "
                             f"{error}") from error
    if not isinstance(document, dict):
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"release metadata from {source} is not an object")
    return document


def _json_list(payload: bytes, source: str) -> list:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"release listing from {source} is not valid JSON: "
                             f"{error}") from error
    if not isinstance(document, list):
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"release listing from {source} is not a list")
    return document


def _asset_url(asset: dict) -> str | None:
    for key in ("url", "browser_download_url"):
        value = asset.get(key)
        if isinstance(value, str) and value.lower().startswith("https://"):
            return value
    return None


def _manifest_asset(document: dict) -> dict | None:
    for asset in document.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == MANIFEST_ASSET_NAME:
            return asset
    return None


def _anchor(asset: dict) -> tuple[str | None, int | None]:
    raw_digest = asset.get("digest")
    if isinstance(raw_digest, str) and raw_digest.startswith("sha256:"):
        digest: str | None = raw_digest.split(":", 1)[1].strip().lower()
    elif isinstance(raw_digest, str) and raw_digest.strip():
        # Present but not sha256:<hex> — kept so verification refuses as
        # malformed metadata instead of missing metadata.
        digest = raw_digest.strip()
    else:
        digest = None
    size = asset.get("size")
    if isinstance(size, bool) or not isinstance(size, int):
        size = None
    return digest, size


def _document_candidate(document: object) -> release_v3lib.ReleaseCandidate | None:
    """A V3 candidate from a GitHub-shaped release document, or None.

    Not a candidate: a draft, a tag that is not SemVer (nothing installable),
    or a release that publishes no V3 manifest asset — that last one is a
    V2-era release, not a broken V3 one.
    """

    from . import version as versionlib

    if not isinstance(document, dict) or document.get("draft"):
        return None
    tag = document.get("tag_name")
    if not isinstance(tag, str):
        return None
    parsed = versionlib.parse(tag)
    if parsed is None:
        return None
    asset = _manifest_asset(document)
    if asset is None:
        return None
    digest, size = _anchor(asset)
    return release_v3lib.ReleaseCandidate(
        version=str(parsed), identity=tag,
        channel="beta" if document.get("prerelease") else "stable",
        manifest_sha256=digest, manifest_size=size,
        manifest_locator=_asset_url(asset))


class _AssetDocumentProvider(release_v3lib.ReleaseProvider):
    """Shared fetching for the providers whose releases are GitHub-shaped."""

    def __init__(self) -> None:
        self._documents: dict[str, dict] = {}

    def _remember(self, candidate: release_v3lib.ReleaseCandidate,
                  document: dict) -> None:
        self._documents[candidate.identity] = document

    def _document(self, candidate: release_v3lib.ReleaseCandidate) -> dict:
        try:
            return self._documents[candidate.identity]
        except KeyError:
            raise LifecycleError(
                "UPDATE_CHECK_FAILED",
                "the provider must enumerate before it fetches") from None

    def _token(self) -> str:
        return ""

    def _get(self, url: str, limit: int) -> bytes:
        return transportlib.get(url, limit=limit, endpoint=self.endpoint,
                                kind=transportlib.ARTIFACT,
                                accept=transportlib.ACCEPT_OCTET_STREAM,
                                token=self._token())

    def fetch_manifest(self, candidate: release_v3lib.ReleaseCandidate) -> bytes:
        locator = candidate.manifest_locator or _asset_url(
            _manifest_asset(self._document(candidate)) or {})
        if not locator:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"release {candidate.identity} publishes no "
                                 f"fetchable {MANIFEST_ASSET_NAME}")
        return self._get(locator, MAX_MANIFEST_BYTES)

    def fetch_artifact(self, candidate: release_v3lib.ReleaseCandidate,
                       artifact: release_v3lib.ManifestArtifact) -> bytes:
        document = self._document(candidate)
        for asset in document.get("assets") or []:
            if isinstance(asset, dict) and asset.get("name") == artifact.name:
                url = _asset_url(asset)
                if url:
                    return self._get(url, MAX_ARCHIVE_BYTES)
        raise LifecycleError(
            "UPDATE_UNAVAILABLE",
            f"release {candidate.identity} publishes no asset {artifact.name!r}")


class GitHubReleaseProvider(_AssetDocumentProvider):
    """GitHub Releases as a V3 source. Auth only at the configured origin."""

    name = "github"

    def __init__(self, endpoint, repository: str = "Rwanbt/ai-native-dev-stack",
                 page_bound: int = MAX_ENUMERATION_ENTRIES) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.repository = repository
        self.page_bound = page_bound

    def _token(self) -> str:
        if self.endpoint.auth_origin is None:
            return ""
        from . import provider as providerlib

        return providerlib.environment_token()

    def enumerate(self, query: release_v3lib.ReleaseQuery) -> release_v3lib.EnumerationResult:
        url = (f"{self.endpoint.api_base_url}/repos/{self.repository}"
               f"/releases?per_page={self.page_bound}")
        payload = transportlib.get(url, limit=MAX_MANIFEST_BYTES, endpoint=self.endpoint,
                                   kind=transportlib.METADATA,
                                   accept=transportlib.ACCEPT_GITHUB_JSON,
                                   token=self._token())
        documents = _json_list(payload, url)
        candidates = []
        for document in documents:
            candidate = _document_candidate(document)
            if candidate is None:
                continue
            self._remember(candidate, document)
            candidates.append(candidate)
        return release_v3lib.EnumerationResult(tuple(candidates),
                                               complete=len(documents) < self.page_bound)


class AnonymousReleaseApiProvider(_AssetDocumentProvider):
    """`AINATIVE_UPDATE_URL`: one release document, anonymous, GitHub-shaped."""

    name = "anonymous"

    def __init__(self, url: str,
                 endpoint: transportlib.ReleaseProviderEndpointConfig | None = None) -> None:
        super().__init__()
        self.url = url
        self.endpoint = endpoint or transportlib.anonymous_endpoint(url)

    def enumerate(self, query: release_v3lib.ReleaseQuery) -> release_v3lib.EnumerationResult:
        payload = transportlib.get(self.url, limit=MAX_MANIFEST_BYTES,
                                   endpoint=self.endpoint,
                                   kind=transportlib.METADATA,
                                   accept=transportlib.ACCEPT_GITHUB_JSON,
                                   token=self._token())
        document = _json_object(payload, self.url)
        candidate = _document_candidate(document)
        if candidate is not None:
            self._remember(candidate, document)
        return release_v3lib.EnumerationResult((candidate,) if candidate else (),
                                               complete=True)


class LocalReleaseProvider(release_v3lib.ReleaseProvider):
    """A local mirror that executes the same logical chain as a network source.

    `releases.json` names, per channel, the version and the manifest locator
    with its size and SHA-256 (`{"manifest": {"file": ..., "size": ...,
    "sha256": ...}}`); the manifest then names the artifacts. A channel entry
    without a V3 manifest paragraph is a V2-era entry and is not a candidate.
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

    def _candidate(self, channel: str, entry: object) -> release_v3lib.ReleaseCandidate | None:
        if not isinstance(entry, dict):
            return None
        version = entry.get("version")
        manifest = entry.get("manifest")
        if not isinstance(version, str) or not version.strip() or not isinstance(manifest, dict):
            return None
        file = manifest.get("file")
        locator = f"{version}/{file}" if isinstance(file, str) and file else None
        sha = manifest.get("sha256")
        size = manifest.get("size")
        return release_v3lib.ReleaseCandidate(
            version=version.strip(), identity=f"local:{channel}", channel=channel,
            manifest_sha256=sha if isinstance(sha, str) else None,
            manifest_size=size if isinstance(size, int) and not isinstance(size, bool) else None,
            manifest_locator=locator)

    def enumerate(self, query: release_v3lib.ReleaseQuery) -> release_v3lib.EnumerationResult:
        index = self._index()
        channels = index.get("channels")
        if not isinstance(channels, dict) or not channels:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"{self.root / 'releases.json'} declares no channels")
        candidates = []
        for channel, entry in sorted(channels.items()):
            candidate = self._candidate(str(channel), entry)
            if candidate is not None:
                candidates.append(candidate)
        return release_v3lib.EnumerationResult(tuple(candidates), complete=True)

    def _release_file(self, relative: str, *, limit: int,
                      description: str) -> bytes:
        parts = validate_relative(relative)
        path = self.root.joinpath(*parts.parts)
        try:
            size = path.stat().st_size
        except OSError as error:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"{description} is missing: {error}") from error
        if size > limit:
            raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                                 f"{description} is {size} bytes, over the "
                                 f"{limit} limit")
        try:
            return path.read_bytes()
        except OSError as error:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"cannot read {description}: {error}") from error

    def fetch_manifest(self, candidate: release_v3lib.ReleaseCandidate) -> bytes:
        if not candidate.manifest_locator:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"{candidate.identity} declares no manifest locator")
        return self._release_file(candidate.manifest_locator, limit=MAX_MANIFEST_BYTES,
                                  description=f"manifest for {candidate.identity}")

    def fetch_artifact(self, candidate: release_v3lib.ReleaseCandidate,
                       artifact: release_v3lib.ManifestArtifact) -> bytes:
        return self._release_file(f"{candidate.version}/{artifact.name}",
                                  limit=MAX_ARCHIVE_BYTES,
                                  description=f"artifact {artifact.name!r}")


class GitLabReleaseProvider(release_v3lib.ReleaseProvider):
    """GitLab.com as a V3 source: Releases for discovery, the Generic Package
    Registry as the canonical distribution and integrity surface (ADR-0019
    section 11).

    Release Link URLs are presentation, never integrity roots: the anchor is
    the package file API's `file_sha256` and `size`. One project identity
    (`release_project_ref`) is used for Releases, packages and package files —
    there is no second project configuration. GitLab is V3-only: it has no V2
    fallback, and a complete channel without a V3 candidate refuses.
    """

    name = "gitlab"
    supports_v2_fallback = False

    def __init__(self, endpoint, project_ref: str,
                 page_bound: int = MAX_ENUMERATION_ENTRIES) -> None:
        self.endpoint = endpoint
        self.project_ref = project_ref
        self.page_bound = page_bound
        self._downloads: dict[str, dict[str, str]] = {}

    # --- requests -------------------------------------------------------

    def _token(self) -> str:
        if self.endpoint.auth_origin is None:
            return ""
        from . import provider as providerlib

        return providerlib.environment_gitlab_token()

    def _project_url(self) -> str:
        encoded = urllib.parse.quote(self.project_ref, safe="")
        return f"{self.endpoint.api_base_url}/projects/{encoded}"

    def _get_json(self, url: str) -> object:
        payload = transportlib.get(url, limit=MAX_MANIFEST_BYTES, endpoint=self.endpoint,
                                   kind=transportlib.METADATA,
                                   accept=transportlib.ACCEPT_JSON,
                                   token=self._token())
        try:
            return json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"GitLab answered {url} with invalid JSON: "
                                 f"{error}") from error

    def _get_bytes(self, url: str, limit: int) -> bytes:
        return transportlib.get(url, limit=limit, endpoint=self.endpoint,
                                kind=transportlib.ARTIFACT,
                                accept=transportlib.ACCEPT_OCTET_STREAM,
                                token=self._token())

    # --- enumeration ----------------------------------------------------

    def enumerate(self, query: release_v3lib.ReleaseQuery) -> release_v3lib.EnumerationResult:
        releases, releases_complete = self._releases()
        packages, packages_complete = self._packages()
        candidates = self._candidates(releases, packages)
        return release_v3lib.EnumerationResult(
            tuple(candidates), complete=releases_complete and packages_complete)

    def _releases(self) -> tuple[list, bool]:
        url = f"{self._project_url()}/releases?per_page={self.page_bound}"
        document = self._get_json(url)
        if not isinstance(document, list):
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"GitLab releases from {url} are not a list")
        return document, len(document) < self.page_bound

    def _packages(self) -> tuple[dict, bool]:
        url = (f"{self._project_url()}/packages?package_type=generic"
               f"&package_name={GITLAB_PACKAGE_NAME}&per_page={self.page_bound}")
        document = self._get_json(url)
        if not isinstance(document, list):
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"GitLab packages from {url} are not a list")
        by_version: dict[str, list] = {}
        for record in document:
            if not isinstance(record, dict):
                continue
            if (record.get("package_type") != "generic"
                    or record.get("name") != GITLAB_PACKAGE_NAME):
                continue
            parsed = versionlib.parse(record.get("version")) \
                if isinstance(record.get("version"), str) else None
            if parsed is None:
                continue
            by_version.setdefault(str(parsed), []).append(record)
        return by_version, len(document) < self.page_bound

    def _candidates(self, releases: list, packages: dict) -> list:
        candidates = []
        for release in releases:
            parsed = versionlib.parse(release.get("tag_name")) \
                if isinstance(release, dict) else None
            if parsed is None or release.get("upcoming_release"):
                continue
            records = packages.get(str(parsed))
            if not records:
                continue
            if len(records) > 1:
                raise LifecycleError(
                    "RELEASE_DUPLICATE_VERSION",
                    f"project {self.project_ref} publishes {len(records)} generic "
                    f"packages for version {parsed}; exactly one is required")
            identity = str(release.get("tag_name"))
            package_id = records[0].get("id")
            files = self._package_files(package_id)
            digest, size = self._anchor(files, identity)
            self._downloads[identity] = self._download_urls(package_id, files)
            candidates.append(release_v3lib.ReleaseCandidate(
                version=str(parsed), identity=identity,
                channel="beta" if parsed.pre else "stable",
                manifest_sha256=digest, manifest_size=size))
        return candidates

    def _package_files(self, package_id: object) -> list:
        url = (f"{self._project_url()}/packages/{package_id}/package_files"
               f"?per_page={self.page_bound}")
        document = self._get_json(url)
        if not isinstance(document, list):
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 f"GitLab package files from {url} are not a list")
        if len(document) >= self.page_bound:
            raise LifecycleError(
                "RELEASE_ENUMERATION_INCOMPLETE",
                f"package {package_id} answered a full page of files; the "
                "listing bounds were reached before exhaustion")
        return [entry for entry in document if isinstance(entry, dict)]

    def _download_urls(self, package_id: object, files: list) -> dict:
        return {str(entry.get("file_name")):
                f"{self._project_url()}/packages/{package_id}/package_files/"
                f"{entry.get('id')}/download"
                for entry in files if entry.get("id") is not None}

    def _anchor(self, files: list, identity: str) -> tuple[str, int]:
        manifests = [entry for entry in files
                     if entry.get("file_name") == MANIFEST_ASSET_NAME]
        if not manifests:
            raise LifecycleError("RELEASE_MANIFEST_MISSING",
                                 f"release {identity} carries no {MANIFEST_ASSET_NAME}")
        if len(manifests) > 1:
            raise LifecycleError("RELEASE_MANIFEST_AMBIGUOUS",
                                 f"release {identity} carries {len(manifests)} "
                                 f"{MANIFEST_ASSET_NAME} files")
        entry = manifests[0]
        digest = entry.get("file_sha256")
        if not isinstance(digest, str) or not digest.strip():
            raise LifecycleError(
                "RELEASE_INTEGRITY_METADATA_MISSING",
                f"package file of release {identity} publishes no file_sha256")
        cleaned = digest.strip().lower()
        if len(cleaned) != 64 or any(character not in "0123456789abcdef"
                                     for character in cleaned):
            raise LifecycleError(
                "RELEASE_INTEGRITY_METADATA_INVALID",
                f"package file of release {identity} carries a malformed file_sha256")
        size = entry.get("size")
        if size is None:
            raise LifecycleError(
                "RELEASE_INTEGRITY_METADATA_MISSING",
                f"package file of release {identity} publishes no size")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise LifecycleError(
                "RELEASE_INTEGRITY_METADATA_INVALID",
                f"package file of release {identity} carries a malformed size")
        return cleaned, size

    # --- fetching -------------------------------------------------------

    def _download(self, identity: str, name: str, limit: int) -> bytes:
        downloads = self._downloads.get(identity)
        if downloads is None:
            raise LifecycleError("UPDATE_CHECK_FAILED",
                                 "the provider must enumerate before it fetches")
        url = downloads.get(name)
        if not url:
            raise LifecycleError("UPDATE_UNAVAILABLE",
                                 f"release {identity} publishes no package file "
                                 f"{name!r}")
        return self._get_bytes(url, limit)

    def fetch_manifest(self, candidate: release_v3lib.ReleaseCandidate) -> bytes:
        return self._download(candidate.identity, MANIFEST_ASSET_NAME,
                              MAX_MANIFEST_BYTES)

    def fetch_artifact(self, candidate: release_v3lib.ReleaseCandidate,
                       artifact: release_v3lib.ManifestArtifact) -> bytes:
        return self._download(candidate.identity, artifact.name, MAX_ARCHIVE_BYTES)


__all__ = ["GitHubReleaseProvider", "AnonymousReleaseApiProvider",
           "LocalReleaseProvider", "GitLabReleaseProvider", "MANIFEST_ASSET_NAME",
           "GITLAB_PACKAGE_NAME", "MAX_MANIFEST_BYTES", "MAX_ARCHIVE_BYTES",
           "MAX_ENUMERATION_ENTRIES"]
