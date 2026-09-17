#!/usr/bin/env python3
"""Decide whether this publication may proceed, from what was actually built.

The V3 bridge gate used to run only when the repository variable
`V3_BRIDGE_RELEASE` was set, so a V3 publication could go out simply because
the variable was forgotten: the absence of the variable was silently treated
as proof that the publication was V2. The publication protocol is now derived
from the **built artifacts** — the absence of the variable is never evidence —
and a protocol 3 publication without a verified bridge blocks the release
(#177).

The bridge itself is resolved through the existing V2 path
(`scripts/check_bridge_release.py` + the production `ReleaseApiProvider`):
there is no second resolver.

Usage:
    python scripts/check_release_gate.py --dist dist
    V3_BRIDGE_RELEASE=2.4.4 python scripts/check_release_gate.py --dist dist --json

Exit codes:
    0  ALLOW  — the publication may proceed
    1  BLOCK  — the publication must not happen
    2  usage / configuration error
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
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

import check_bridge_release  # noqa: E402

ENV_VAR = check_bridge_release.ENV_VAR
V3_MANIFEST_NAME = "ainative-release-v3.json"
V3_BUNDLE_PREFIX = "ainative-lifecycle-v3-"
V3_BUNDLE_SUFFIX = ".zip"

ALLOW = "ALLOW"
BLOCK = "BLOCK"


def publication_protocol(dist: Path) -> int:
    """The lifecycle protocol this publication actually carries.

    3 when a V3 manifest or V3 lifecycle bundle was built; 2 otherwise. The
    artifacts decide — never an environment variable.
    """

    if not dist.is_dir():
        return 2
    for entry in sorted(dist.iterdir()):
        name = entry.name
        if name == V3_MANIFEST_NAME:
            return 3
        if name.startswith(V3_BUNDLE_PREFIX) and name.endswith(V3_BUNDLE_SUFFIX):
            return 3
    return 2


def evaluate(dist: Path, bridge_version: str, *,
             verify=check_bridge_release.verify_bridge_release) -> dict:
    """The gate decision, as a record. Never raises for a refusal."""

    protocol = publication_protocol(dist)
    if protocol < 3:
        return {"protocol": protocol, "bridge": "not-applicable", "decision": ALLOW,
                "detail": "no V3 lifecycle artifact was built; the bridge gate "
                          "does not apply"}
    if not (bridge_version or "").strip():
        return {"protocol": protocol, "bridge": "missing", "decision": BLOCK,
                "detail": f"a protocol 3 publication requires {ENV_VAR}; "
                          "the absence of the variable is never proof of a V2 "
                          "publication"}
    try:
        record = verify(bridge_version.strip())
    except check_bridge_release.BridgeReleaseUnverified as error:
        return {"protocol": protocol, "bridge": "unverified", "decision": BLOCK,
                "detail": str(error)}
    return {"protocol": protocol, "bridge": "verified", "decision": ALLOW,
            "detail": f"bridge release {record.get('bridge_version')} is "
                      "verifiable by a V2 runtime", "record": record}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", required=True,
                        help="the directory holding the built release artifacts")
    parser.add_argument("--bridge-version", default=os.environ.get(ENV_VAR, ""),
                        help=f"the declared bridge release; defaults to ${ENV_VAR}")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    if not dist.is_dir():
        print(f"configuration error: no such dist directory: {dist}", file=sys.stderr)
        return 2
    outcome = evaluate(dist, args.bridge_version)
    if args.json:
        print(json.dumps(outcome, indent=2, sort_keys=True))
    if outcome["decision"] == BLOCK:
        print(f"BLOCK RELEASE: {outcome['detail']}", file=sys.stderr)
        return 1
    print(f"gate: {outcome['decision']} — protocol {outcome['protocol']}; "
          f"{outcome['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
