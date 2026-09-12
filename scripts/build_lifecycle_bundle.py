#!/usr/bin/env python3
"""Build the lifecycle bundle published with every release.

The official update path consumes `ainative-dev-stack-<version>.zip`: the
installer payload — exactly the files `source.py` and the manifest expect —
packed at the archive root, so `_distribution_root()` finds `VERSION` without
guessing. This is the only artifact `ainative update` downloads, and its
SHA-256 travels in the release metadata (asset digest) and in SHA256SUMS.

Usage:
    python scripts/build_lifecycle_bundle.py [--outdir dist]

Refuses to build when VERSION and ainative.__version__ disagree (#125).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from _payload_staging import assert_version_consistency, stage_payload  # noqa: E402

# A fixed timestamp so rebuilding the same tree does not produce a different
# archive only because of file mtimes.
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def build(outdir: Path) -> Path:
    """Pack the staged payload into `ainative-dev-stack-<version>.zip`."""

    version = assert_version_consistency(REPO)
    outdir.mkdir(parents=True, exist_ok=True)
    bundle = outdir / f"ainative-dev-stack-{version}.zip"
    with tempfile.TemporaryDirectory(prefix="ainative-bundle-") as staging:
        payload = stage_payload(REPO, Path(staging) / "payload")
        entries = sorted(path for path in payload.rglob("*") if path.is_file())
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in entries:
                info = zipfile.ZipInfo(path.relative_to(payload).as_posix(),
                                       date_time=FIXED_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
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