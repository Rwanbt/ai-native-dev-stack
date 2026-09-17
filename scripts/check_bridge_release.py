#!/usr/bin/env python3
"""Block a V3 publication until its V2 bridge release is verifiable.

A V3 lifecycle publication cannot be applied by any runtime older than V3.
Every installed runtime must therefore be able to cross to the bridge release
first, and "the bridge exists" must be checked the way a user's updater checks
it — by resolving the release through the V2 selection rules, digest included —
not by trusting a tag name. This is the gate the V3 release pipeline runs
before publishing (PR-0B, #157); a missing, unpublished or bundle-less bridge
release blocks the release.

The check is read-only: it resolves release metadata and downloads nothing.

Usage:
    V3_BRIDGE_RELEASE=2.5.0 python scripts/check_bridge_release.py
    python scripts/check_bridge_release.py --bridge-version 2.5.0 --json

Exit codes:
    0  the bridge release is verifiable; the publication may proceed
    1  BLOCK RELEASE — missing, unpublished or unusable bridge release
    2  configuration error — no bridge version declared
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ainative.lifecycle import provider as providerlib  # noqa: E402
from ainative.lifecycle import version as versionlib  # noqa: E402
from ainative.lifecycle.errors import LifecycleError  # noqa: E402

ENV_VAR = "V3_BRIDGE_RELEASE"
DEFAULT_RELEASE_API = ("https://api.github.com/repos/Rwanbt/"
                       "ai-native-dev-stack/releases/tags/v{version}")


class BridgeReleaseUnverified(Exception):
    """The publication must block; the message says exactly why."""


def release_document_url(version: str, template: str = DEFAULT_RELEASE_API) -> str:
    return template.format(version=version)


def verify_bridge_release(version: str, *, provider=None,
                          release_api: str = DEFAULT_RELEASE_API) -> dict:
    """Resolve `version` as a V2 runtime would, and require a published bundle.

    The resolution walks the production selection path
    (`ReleaseProvider.latest`), so "verifiable" means exactly what it means to
    a user: a V2 runtime selects this bundle with a published digest. A
    future-protocol release is not a bridge — a V2 runtime could not apply it
    either (`CLI_UPDATE_REQUIRED`), and that refusal blocks here too.
    """

    parsed = versionlib.parse(version)
    if parsed is None:
        raise BridgeReleaseUnverified(f"bridge version {version!r} is not SemVer")
    provider = provider or providerlib.ReleaseApiProvider(
        release_document_url(str(parsed), release_api))
    try:
        release = provider.latest("stable")
    except LifecycleError as error:
        raise BridgeReleaseUnverified(
            f"a V2 runtime cannot resolve the bridge release {parsed}: "
            f"{error.code}: {error.message}") from error
    if release.version != str(parsed):
        raise BridgeReleaseUnverified(
            f"the release behind {parsed} declares version {release.version!r}")
    if not release.digest:
        raise BridgeReleaseUnverified(
            f"bridge release {parsed} publishes no bundle digest; a runtime "
            "cannot verify what it would install")
    return {"bridge_version": str(parsed),
            "lifecycle_bundle": providerlib.lifecycle_bundle_name(str(parsed)),
            "sha256": release.digest,
            "source": release.source}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bridge-version", default=os.environ.get(ENV_VAR, ""),
                        help=f"V2-compatible bridge release; defaults to ${ENV_VAR}")
    parser.add_argument("--release-api", default=DEFAULT_RELEASE_API,
                        help="release document URL template containing {version}")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    version = args.bridge_version.strip()
    if not version:
        print(f"BLOCK RELEASE: declare the bridge release with {ENV_VAR} "
              "or --bridge-version", file=sys.stderr)
        return 2
    try:
        record = verify_bridge_release(version, release_api=args.release_api)
    except BridgeReleaseUnverified as error:
        print(f"BLOCK RELEASE: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(f"bridge release {record['bridge_version']} verified: "
              f"{record['lifecycle_bundle']} sha256:{record['sha256'][:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
