#!/usr/bin/env python3
"""Build the lifecycle bundle published with every release.

The official update path consumes
`ainative-lifecycle-v2-<version>.zip`: a protocol document at the archive root,
the installer payload under `stack/`, and a `protocol/` directory that describes
the format. The wrapping is deliberate. Runtimes up to v2.2.2 selected any
`ainative-dev-stack-*.zip` and found the payload by looking for a single
top-level directory with a VERSION file; this layout names another file and
ships two top-level directories, so a legacy runtime refuses it even when a
mirror hands it the file directly (AUD-205).

Refuses to build when VERSION and ainative.__version__ disagree (#125).

Usage:
    python scripts/build_lifecycle_bundle.py [--outdir dist]
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
from ainative.lifecycle.provider import (PROTOCOL_MANIFEST,  # noqa: E402
                                         lifecycle_bundle_name, protocol_document)

# A fixed timestamp so rebuilding the same tree does not produce a different
# archive only because of file mtimes.
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)

PROTOCOL_README = """# Lifecycle bundle protocol v2

The payload this archive carries is installed by a lifecycle runtime that
speaks protocol v2. The layout is:

    lifecycle-protocol.json   protocol version, release version, payload root
    stack/                    the distribution payload (VERSION at its root)
    protocol/                 this document

A runtime older than v2.2.2 selects bundles by the `ainative-dev-stack-*` name
and looks for the payload in a single top-level directory. It therefore cannot
consume this archive - by design. Upgrade the CLI first.
"""


def _write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def build(outdir: Path) -> Path:
    """Pack the staged payload into the v2 lifecycle bundle for this tree."""

    version = assert_version_consistency(REPO)
    outdir.mkdir(parents=True, exist_ok=True)
    bundle = outdir / lifecycle_bundle_name(version)
    with tempfile.TemporaryDirectory(prefix="ainative-bundle-") as staging:
        payload = stage_payload(REPO, Path(staging) / "payload")
        entries = sorted(path for path in payload.rglob("*") if path.is_file())
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            _write(archive, PROTOCOL_MANIFEST,
                   (json.dumps(protocol_document(version), indent=2, sort_keys=True)
                    + "\n").encode("utf-8"))
            _write(archive, "protocol/README.md", PROTOCOL_README.encode("utf-8"))
            for path in entries:
                _write(archive, f"stack/{path.relative_to(payload).as_posix()}",
                       path.read_bytes())
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--outdir", default="dist", help="where to write the bundle")
    args = parser.parse_args()
    bundle = build(Path(args.outdir))
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    print(f"bundle: {bundle}")
    print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())