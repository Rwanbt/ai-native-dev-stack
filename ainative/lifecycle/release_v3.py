"""Release V3: the provider contract, the manifest, and the chains that bind them.

ADR-0019 sections 7–10. Three ideas, each fail-closed:

* A candidate is installable only when its version is SemVer without build
  metadata, and two candidates must not claim the same precedence with
  different identities (`RELEASE_DUPLICATE_VERSION`).
* An enumeration that stopped at its bounds is incomplete
  (`RELEASE_ENUMERATION_INCOMPLETE`); a complete channel with nothing is
  `RELEASE_NO_CANDIDATE`. Partial results are never used silently.
* The manifest's SHA-256 and size come from provider metadata, never from the
  manifest itself: they are verified **before** the document is parsed, so
  nothing a hostile manifest says can influence whether its own bytes are
  trusted. The version chain then requires one version across candidate,
  manifest, compatibility.runtime_version, artifact, artifact filename and the
  lifecycle protocol document.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable

from . import version as versionlib
from .digest import digest_bytes
from .errors import LifecycleError

MANIFEST_SCHEMA = "ainative.release"
MANIFEST_PROTOCOL = "v3"
ARTIFACT_KIND_LIFECYCLE = "lifecycle"
ARTIFACT_KINDS = (ARTIFACT_KIND_LIFECYCLE,)

_V3_BUNDLE_PREFIX = "ainative-lifecycle-v3-"
_V3_BUNDLE_SUFFIX = ".zip"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReleaseQuery:
    """What a caller asks a provider for: one compatible channel."""

    channel: str = "stable"


@dataclass(frozen=True)
class ReleaseCandidate:
    """One enumerated release, with the anchor of its manifest.

    `manifest_sha256` and `manifest_size` are the external integrity anchor:
    they come from the provider's own metadata (a release asset listing, a
    mirror index), never from the manifest bytes themselves.
    `manifest_locator` is the provider-internal way to fetch the manifest
    (an asset API URL, a mirror path); it is opaque to this module.
    """

    version: str
    identity: str
    channel: str = "stable"
    manifest_sha256: str | None = None
    manifest_size: int | None = None
    manifest_locator: str | None = None

    def to_record(self) -> dict:
        return {"version": self.version, "identity": self.identity,
                "channel": self.channel,
                "manifest_sha256": self.manifest_sha256,
                "manifest_size": self.manifest_size}


@dataclass(frozen=True)
class EnumerationResult:
    """Everything the provider could see, and whether that was everything."""

    candidates: tuple[ReleaseCandidate, ...]
    complete: bool

    def to_record(self) -> dict:
        return {"complete": self.complete,
                "candidates": [candidate.to_record() for candidate in self.candidates]}


@dataclass(frozen=True)
class ManifestArtifact:
    """One artifact the manifest declares. Verified, never trusted."""

    name: str
    kind: str
    version: str
    sha256: str
    size: int

    def to_record(self) -> dict:
        return {"name": self.name, "kind": self.kind, "version": self.version,
                "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class ReleaseManifest:
    """The parsed ReleaseManifest V3, already validated."""

    version: str
    channel: str
    runtime_version: str
    artifacts: tuple[ManifestArtifact, ...]
    provenance: dict = field(default_factory=dict)
    schema: str = MANIFEST_SCHEMA
    protocol: str = MANIFEST_PROTOCOL

    def lifecycle_artifact(self) -> ManifestArtifact:
        matches = [artifact for artifact in self.artifacts
                   if artifact.kind == ARTIFACT_KIND_LIFECYCLE]
        if len(matches) != 1:
            raise LifecycleError(
                "UPDATE_INTEGRITY_FAILED",
                f"the manifest declares {len(matches)} lifecycle artifacts; "
                "exactly one is required")
        return matches[0]

    def to_record(self) -> dict:
        return {"schema": self.schema, "protocol": self.protocol,
                "version": self.version, "channel": self.channel,
                "compatibility": {"runtime_version": self.runtime_version},
                "artifacts": [artifact.to_record() for artifact in self.artifacts],
                "provenance": dict(self.provenance)}


class ReleaseProvider:
    """The V3 provider contract. Implementations fetch; this module decides."""

    name = "abstract"

    def enumerate(self, query: ReleaseQuery) -> EnumerationResult:
        raise NotImplementedError

    def fetch_manifest(self, candidate: ReleaseCandidate) -> bytes:
        raise NotImplementedError

    def fetch_artifact(self, candidate: ReleaseCandidate,
                       artifact: ManifestArtifact) -> bytes:
        raise NotImplementedError


def canonical_version(value: object) -> str:
    """A SemVer version string without build metadata, or a refusal.

    `1.2.3` and `1.2.3-rc.1` are installable; `1.2.3+build1` is refused with
    `RELEASE_BUILD_METADATA_UNSUPPORTED` because two artifacts must never share
    an installable version identity. A value that is not SemVer at all keeps
    the historical `UPDATE_CHECK_FAILED` refusal.
    """

    parsed = versionlib.parse(value) if isinstance(value, str) else None
    if parsed is None:
        raise LifecycleError("UPDATE_CHECK_FAILED",
                             f"release version {value!r} is not a SemVer version")
    if "+" in parsed.raw:
        raise LifecycleError(
            "RELEASE_BUILD_METADATA_UNSUPPORTED",
            f"release version {parsed.raw!r} carries build metadata; installable "
            "versions are exactly major.minor.patch with an optional pre-release",
            version=parsed.raw)
    return str(parsed)


def select_candidate(result: EnumerationResult, query: ReleaseQuery) -> ReleaseCandidate:
    """The newest installable candidate of the channel, or a refusal."""

    if not result.complete:
        raise LifecycleError(
            "RELEASE_ENUMERATION_INCOMPLETE",
            "the provider stopped enumerating at its bounds; partial results "
            "are never used to pick a release")
    compatible = [candidate for candidate in result.candidates
                  if candidate.channel == query.channel]
    if not compatible:
        raise LifecycleError(
            "RELEASE_NO_CANDIDATE",
            f"the {query.channel!r} channel is complete and holds no release")
    by_precedence: dict[str, str] = {}
    for candidate in compatible:
        canonical = canonical_version(candidate.version)
        previous = by_precedence.get(canonical)
        if previous is not None and previous != candidate.identity:
            raise LifecycleError(
                "RELEASE_DUPLICATE_VERSION",
                f"two releases claim version {canonical}: {previous!r} and "
                f"{candidate.identity!r}; duplicates are never resolved by order",
                version=canonical, identities=sorted({previous, candidate.identity}))
        by_precedence[canonical] = candidate.identity
    ordered = sorted(compatible, key=lambda candidate: versionlib.parse(candidate.version))
    return ordered[-1]


def verify_external_anchor(payload: bytes, *, sha256: str | None, size: int | None) -> None:
    """Verify bytes against the anchor that travelled with the candidate.

    Absent anchor: `RELEASE_INTEGRITY_METADATA_MISSING`; malformed:
    `RELEASE_INTEGRITY_METADATA_INVALID`; anything that does not match:
    `UPDATE_INTEGRITY_FAILED`. This runs BEFORE parsing, always.
    """

    if sha256 is None and size is None:
        raise LifecycleError(
            "RELEASE_INTEGRITY_METADATA_MISSING",
            "the provider published no manifest digest and size; a manifest "
            "nobody anchored is not one this stack parses")
    if not (isinstance(sha256, str) and _SHA256.match(sha256.strip().lower())
            and isinstance(size, int) and not isinstance(size, bool) and size > 0):
        raise LifecycleError(
            "RELEASE_INTEGRITY_METADATA_INVALID",
            f"the manifest anchor is malformed (sha256={sha256!r}, size={size!r})")
    if len(payload) != size:
        raise LifecycleError(
            "UPDATE_INTEGRITY_FAILED",
            f"the manifest is {len(payload)} bytes but the provider declared {size}")
    actual = digest_bytes(payload)
    if actual != sha256.strip().lower():
        raise LifecycleError(
            "UPDATE_INTEGRITY_FAILED",
            f"the manifest digest {actual} does not match the anchored "
            f"{sha256.strip().lower()}",
            expected=sha256.strip().lower(), actual=actual)


def parse_manifest(payload: bytes) -> ReleaseManifest:
    """Parse and validate a manifest whose bytes were already verified."""

    try:
        document = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"the manifest is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED", "the manifest is not an object")
    if document.get("schema") != MANIFEST_SCHEMA:
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"unknown manifest schema {document.get('schema')!r}")
    protocol = document.get("protocol")
    if protocol != MANIFEST_PROTOCOL:
        newer = _newer_protocol(protocol)
        if newer is not None:
            raise LifecycleError(
                "CLI_UPDATE_REQUIRED",
                f"the release manifest speaks protocol {protocol}; this runtime "
                "speaks v3 and the release must be applied by a newer CLI runtime")
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"unknown manifest protocol {protocol!r}")

    raw_version = document.get("version")
    if not isinstance(raw_version, str) or not raw_version.strip():
        raise LifecycleError("UPDATE_INTEGRITY_FAILED", "the manifest declares no version")
    version = canonical_version(raw_version)
    channel = document.get("channel")
    if not isinstance(channel, str) or not channel.strip():
        raise LifecycleError("UPDATE_INTEGRITY_FAILED", "the manifest declares no channel")
    compatibility = document.get("compatibility")
    if not isinstance(compatibility, dict):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             "the manifest declares no compatibility object")
    raw_runtime = compatibility.get("runtime_version")
    if not isinstance(raw_runtime, str) or not raw_runtime.strip():
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             "the manifest declares no compatibility.runtime_version")
    runtime_version = canonical_version(raw_runtime)
    artifacts = _parse_artifacts(document.get("artifacts"))
    provenance = document.get("provenance", {})
    if not isinstance(provenance, dict):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED", "provenance must be an object")
    return ReleaseManifest(version=version, channel=channel.strip(),
                           runtime_version=runtime_version, artifacts=artifacts,
                           provenance=dict(provenance))


def _newer_protocol(protocol: object) -> int | None:
    """The protocol number when it is a v<N> newer than this runtime's, else None."""

    match = re.match(r"^v(?P<number>\d+)$", str(protocol))
    if match is None:
        return None
    number = int(match.group("number"))
    return number if number > int(MANIFEST_PROTOCOL.lstrip("v")) else None


def _parse_artifacts(raw: object) -> tuple[ManifestArtifact, ...]:
    if not isinstance(raw, list) or not raw:
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             "the manifest declares no artifacts")
    artifacts = []
    for entry in raw:
        artifacts.append(_parse_artifact(entry))
    return tuple(artifacts)


def _parse_artifact(entry: object) -> ManifestArtifact:
    if not isinstance(entry, dict):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED", "an artifact entry is not an object")
    name = entry.get("name")
    if not isinstance(name, str) or not name or "/" in name or "\\" in name \
            or name in (".", ".."):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"artifact name {name!r} is not a plain filename")
    kind = entry.get("kind")
    if kind not in ARTIFACT_KINDS:
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"artifact {name!r} declares unknown kind {kind!r}")
    version = canonical_version(entry.get("version"))
    sha = entry.get("sha256")
    if not (isinstance(sha, str) and _SHA256.match(sha.strip().lower())):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"artifact {name!r} declares no valid sha256")
    size = entry.get("size")
    if not (isinstance(size, int) and not isinstance(size, bool) and size > 0):
        raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                             f"artifact {name!r} declares no valid size")
    return ManifestArtifact(name=name, kind=kind, version=version,
                            sha256=sha.strip().lower(), size=size)


def lifecycle_bundle_name(version: str) -> str:
    """The one filename a V3 lifecycle bundle of `version` may wear."""

    return f"{_V3_BUNDLE_PREFIX}{version}{_V3_BUNDLE_SUFFIX}"


def require_exact_version_chain(candidate: ReleaseCandidate, manifest: ReleaseManifest,
                                artifact: ManifestArtifact, *,
                                protocol_release_version: str | None = None) -> None:
    """One version across every trust-bearing identity, or `UPDATE_VERSION_MISMATCH`.

    candidate.version == manifest.version == manifest.compatibility.runtime_version
    == artifact.version == the artifact filename version == (after extraction)
    lifecycle-protocol.json.release_version.
    """

    links = [
        ("candidate version", candidate.version),
        ("manifest version", manifest.version),
        ("compatibility.runtime_version", manifest.runtime_version),
        ("artifact version", artifact.version),
        ("artifact filename version", _filename_version(artifact)),
    ]
    if protocol_release_version is not None:
        links.append(("lifecycle-protocol.json release_version",
                      protocol_release_version))
    distinct = {value for _, value in links}
    if len(distinct) != 1:
        raise LifecycleError(
            "UPDATE_VERSION_MISMATCH",
            "; ".join(f"{label}={value!r}" for label, value in links),
            chain={label: value for label, value in links})
    if artifact.name != lifecycle_bundle_name(artifact.version):
        raise LifecycleError(
            "UPDATE_VERSION_MISMATCH",
            f"the artifact is named {artifact.name!r} but its version "
            f"{artifact.version!r} requires {lifecycle_bundle_name(artifact.version)!r}",
            published=artifact.name,
            expected=lifecycle_bundle_name(artifact.version))


def _filename_version(artifact: ManifestArtifact) -> str:
    name = artifact.name
    inner = name[len(_V3_BUNDLE_PREFIX):-len(_V3_BUNDLE_SUFFIX)] \
        if name.startswith(_V3_BUNDLE_PREFIX) and name.endswith(_V3_BUNDLE_SUFFIX) \
        else name
    return inner


def resolve_manifest(provider: ReleaseProvider, query: ReleaseQuery
                     ) -> tuple[ReleaseCandidate, ReleaseManifest]:
    """enumerate -> select -> anchor-verified manifest -> exact chain.

    The order is the trust order (ADR-0019 section 9): the manifest's bytes are
    verified against provider metadata before the document is parsed, and the
    version chain is checked before anything is downloaded.
    """

    result = provider.enumerate(query)
    candidate = select_candidate(result, query)
    payload = provider.fetch_manifest(candidate)
    verify_external_anchor(payload, sha256=candidate.manifest_sha256,
                           size=candidate.manifest_size)
    manifest = parse_manifest(payload)
    artifact = manifest.lifecycle_artifact()
    require_exact_version_chain(candidate, manifest, artifact)
    return candidate, manifest


__all__ = [
    "ReleaseQuery", "ReleaseCandidate", "EnumerationResult", "ManifestArtifact",
    "ReleaseManifest", "ReleaseProvider", "canonical_version", "select_candidate",
    "verify_external_anchor", "parse_manifest", "lifecycle_bundle_name",
    "require_exact_version_chain", "resolve_manifest",
    "MANIFEST_SCHEMA", "MANIFEST_PROTOCOL", "ARTIFACT_KIND_LIFECYCLE",
]
