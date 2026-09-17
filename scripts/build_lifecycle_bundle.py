#!/usr/bin/env python3
"""Build the lifecycle bundle published with every release.

Two generations share this builder, and the caller says which one is being
published:

* **protocol 2** (the historical shape, kept for reproducing a bridge) —
  `ainative-lifecycle-v2-<version>.zip`: a protocol document at the archive
  root, the installer payload under `stack/`, and a `protocol/` directory.
  Runtimes up to v2.2.2 selected any `ainative-dev-stack-*.zip` and found the
  payload by looking for a single top-level directory with a VERSION file;
  this layout names another file and ships two top-level directories, so a
  legacy runtime refuses it even when a mirror hands it the file directly
  (AUD-205).
* **protocol 3** (the default since the Release V3 conversion) —
  `ainative-lifecycle-v3-<version>.zip` plus the external
  `ainative-release-v3.json` manifest that anchors it: schema, protocol,
  version, channel, `compatibility.runtime_version`, the artifact's name,
  version, SHA-256 and byte size, and its provenance. The runtime verifies the
  manifest against provider metadata (its SHA-256 and size, obtained from the
  release assets) *before* it parses anything, and the exact version chain must
  hold end to end (ADR-0019).

Refuses to build when VERSION and ainative.__version__ disagree (#125).

Usage:
    python scripts/build_lifecycle_bundle.py [--outdir dist] [--protocol {2,3}]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from _payload_staging import assert_version_consistency, stage_payload  # noqa: E402
from ainative.lifecycle import release_v3 as release_v3lib  # noqa: E402
from ainative.lifecycle.provider import (PROTOCOL_MANIFEST,  # noqa: E402
                                         lifecycle_bundle_name, protocol_document)

# A fixed timestamp so rebuilding the same tree does not produce a different
# archive only because of file mtimes.
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)

PROTOCOL_V2 = 2
PROTOCOL_V3 = 3
V3_MANIFEST_NAME = release_v3lib.MANIFEST_ASSET_NAME

PROTOCOL_README = {
    PROTOCOL_V2: """# Lifecycle bundle protocol v2

The payload this archive carries is installed by a lifecycle runtime that
speaks protocol v2. The layout is:

    lifecycle-protocol.json   protocol version, release version, payload root
    stack/                    the distribution payload (VERSION at its root)
    protocol/                 this document

A runtime older than v2.2.2 selects bundles by the `ainative-dev-stack-*` name
and looks for the payload in a single top-level directory. It therefore cannot
consume this archive - by design. Upgrade the CLI first.
""",
    PROTOCOL_V3: """# Lifecycle bundle protocol v3

The payload this archive carries is installed by a lifecycle runtime that
speaks protocol v3. The layout is:

    lifecycle-protocol.json   protocol version 3, release version, payload root
    stack/                    the distribution payload (VERSION at its root)
    protocol/                 this document

The release also publishes `ainative-release-v3.json`, whose SHA-256 and size
are obtained from the release assets (the external anchor) and verified before
the manifest is parsed. A protocol 2 runtime reports `CLI_UPDATE_REQUIRED` for
this release: upgrade the CLI through the bridge release first.
""",
}


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def _bundle_name(version: str, protocol: int) -> str:
    if protocol == PROTOCOL_V3:
        return release_v3lib.lifecycle_bundle_name(version)
    return lifecycle_bundle_name(version)


def _protocol_payload(version: str, protocol: int) -> dict:
    if protocol == PROTOCOL_V3:
        return {"schema_name": "lifecycle_protocol", "protocol_version": PROTOCOL_V3,
                "release_version": version, "payload_root": "stack"}
    return protocol_document(version)


def build(outdir: Path, protocol: int = PROTOCOL_V3) -> tuple[Path, Path | None]:
    """Pack the staged payload and return (bundle, manifest-or-None)."""

    if protocol not in (PROTOCOL_V2, PROTOCOL_V3):
        raise ValueError(f"unknown lifecycle protocol {protocol!r}")
    version = assert_version_consistency(REPO)
    outdir.mkdir(parents=True, exist_ok=True)
    bundle = outdir / _bundle_name(version, protocol)
    with tempfile.TemporaryDirectory(prefix="ainative-bundle-") as staging:
        payload = stage_payload(REPO, Path(staging) / "payload")
        entries = sorted(path for path in payload.rglob("*") if path.is_file())
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            _write(archive, PROTOCOL_MANIFEST,
                   (json.dumps(_protocol_payload(version, protocol), indent=2,
                               sort_keys=True) + "\n").encode("utf-8"))
            _write(archive, "protocol/README.md",
                   PROTOCOL_README[protocol].encode("utf-8"))
            for path in entries:
                _write(archive, f"stack/{path.relative_to(payload).as_posix()}",
                       path.read_bytes())
    if protocol == PROTOCOL_V2:
        return bundle, None
    data = bundle.read_bytes()
    manifest = {
        "schema": release_v3lib.MANIFEST_SCHEMA,
        "protocol": release_v3lib.MANIFEST_PROTOCOL,
        "version": version,
        "channel": "stable",
        "compatibility": {"runtime_version": version},
        "artifacts": [{"name": bundle.name, "kind": release_v3lib.ARTIFACT_KIND_LIFECYCLE,
                       "version": version,
                       "sha256": hashlib.sha256(data).hexdigest(),
                       "size": len(data)}],
        "provenance": {"source": "release pipeline",
                       "repository": "Rwanbt/ai-native-dev-stack"},
    }
    manifest_path = outdir / V3_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return bundle, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--outdir", default="dist", help="where to write the bundle")
    parser.add_argument("--protocol", type=int, choices=(PROTOCOL_V2, PROTOCOL_V3),
                        default=PROTOCOL_V3,
                        help="lifecycle protocol to build (default: 3)")
    args = parser.parse_args()
    bundle, manifest = build(Path(args.outdir), args.protocol)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    print(f"bundle: {bundle}")
    print(f"sha256: {digest}")
    if manifest is not None:
        print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
