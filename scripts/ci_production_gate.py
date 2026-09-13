#!/usr/bin/env python3
"""The single required status on main: every blocking CI job must have succeeded.

`ci.yml` runs the suites; this aggregate is the one check the branch protection
requires, so a job cannot merge while failed, cancelled or unexpectedly
skipped, and a job that should have been in the gate but is missing from the
payload fails too — absence is not success.

The needs payload arrives as JSON in PRODUCTION_GATE_NEEDS (the workflow passes
`${{ toJSON(needs) }}`), and the blocking list arrives in
PRODUCTION_GATE_EXPECTED (space-separated). Keeping the list in the workflow
and asserting it here makes the gate self-describing; the static test
`tests/test_ci_production_gate.py` pins the two together with the workflow.
"""

from __future__ import annotations

import json
import os
import sys

ALLOWED_RESULTS = frozenset({"success"})


def evaluate(payload: dict, expected: list[str]) -> tuple[bool, list[str]]:
    """Return (ok, problems). Every expected job must be present and successful."""

    problems: list[str] = []
    for job in expected:
        entry = payload.get(job)
        if entry is None:
            problems.append(f"{job}: missing from the needs payload")
            continue
        result = entry.get("result") if isinstance(entry, dict) else None
        if result not in ALLOWED_RESULTS:
            problems.append(f"{job}: {result}")
    return (not problems), problems


def main() -> int:
    raw = os.environ.get("PRODUCTION_GATE_NEEDS", "")
    expected = os.environ.get("PRODUCTION_GATE_EXPECTED", "").split()
    if not raw or not expected:
        print("production gate: PRODUCTION_GATE_NEEDS and "
              "PRODUCTION_GATE_EXPECTED must both be set", file=sys.stderr)
        return 2
    try:
        payload = json.loads(raw)
    except ValueError as error:
        print(f"production gate: cannot parse the needs payload: {error}",
              file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("production gate: the needs payload is not an object", file=sys.stderr)
        return 2
    ok, problems = evaluate(payload, expected)
    if ok:
        print(f"Production Gate: all {len(expected)} blocking job(s) succeeded.")
        return 0
    print("Production Gate FAILED:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
