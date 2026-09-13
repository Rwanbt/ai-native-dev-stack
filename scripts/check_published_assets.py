#!/usr/bin/env python3
"""Verify what a release actually published, before it is made visible.

A release that is uploaded asset by asset is briefly a published release with
a partial set: a user installing during that window gets whatever arrived
first. The workflow therefore creates the release as a *draft*, uploads
everything, and runs this check before flipping it visible. The check compares
the assets GitHub reports - name, size and, when the platform provides it,
digest - against the bytes in `dist/`. A missing asset, a size mismatch or a
digest mismatch keeps the release a draft.

Usage:
    gh release view v2.3.0 --json assets > assets.json
    python scripts/check_published_assets.py --dist dist --assets-json assets.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


class PublishedAssetMismatch(RuntimeError):
    """The published set does not match the built set."""


def local_assets(dist: Path) -> dict[str, dict]:
    assets: dict[str, dict] = {}
    for path in sorted(dist.iterdir()):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        assets[path.name] = {"size": len(payload),
                             "sha256": hashlib.sha256(payload).hexdigest()}
    if not assets:
        raise PublishedAssetMismatch(f"no files in {dist}")
    return assets


def compare(dist: Path, published: list) -> list[str]:
    expected = local_assets(dist)
    seen: dict[str, dict] = {}
    for asset in published:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise PublishedAssetMismatch(f"malformed asset record: {asset!r}")
        seen[asset["name"]] = asset

    missing = sorted(set(expected) - set(seen))
    if missing:
        raise PublishedAssetMismatch(f"assets missing from the release: {missing}")
    extra = sorted(set(seen) - set(expected))
    if extra:
        raise PublishedAssetMismatch(f"assets on the release that were not built: {extra}")

    checked: list[str] = []
    for name, wanted in expected.items():
        published_asset = seen[name]
        if published_asset.get("size") != wanted["size"]:
            raise PublishedAssetMismatch(
                f"{name}: published size {published_asset.get('size')} != built size "
                f"{wanted['size']}")
        digest = published_asset.get("digest")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            if digest.split(":", 1)[1].lower() != wanted["sha256"]:
                raise PublishedAssetMismatch(
                    f"{name}: published digest does not match the built bytes")
        checked.append(name)
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--assets-json", type=Path, required=True)
    args = parser.parse_args()

    published = json.loads(args.assets_json.read_text(encoding="utf-8"))
    if isinstance(published, dict):
        published = published.get("assets")
    if not isinstance(published, list):
        print("PUBLISHED_ASSETS_INVALID: no asset list in the JSON", file=sys.stderr)
        return 1
    try:
        checked = compare(args.dist, published)
    except PublishedAssetMismatch as refusal:
        print(f"PUBLISHED_ASSETS_MISMATCH: {refusal}", file=sys.stderr)
        return 1
    print(f"published assets verified: {', '.join(checked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())