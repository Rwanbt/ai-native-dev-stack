#!/usr/bin/env python3
"""validate_conventions.py — Keep conventions.json aligned with AGENTS.md.

AGENTS.md is the human-readable source for the size/complexity rules;
conventions.json is what the tooling actually enforces. When the two drift,
a rule is enforced at a value it does not declare — which is exactly how the
`>25 blocking` complexity rule ended up implemented as `20` and the
`>200 blocking` function-size rule ended up not implemented at all.

This script fails (exit 1) on any mismatch. Run it in CI.

Usage:
    python3 scripts/validate_conventions.py [--stack-root PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Each rule maps an AGENTS.md bullet to the conventions.json keys it governs.
# `numbers` is the ordered list of integers expected on the bullet line.
RULES = [
    {
        "bullet": "File size",
        "section": "file_size",
        "keys": ["new_file_warning", "existing_file_warning", "blocking"],
    },
    {
        "bullet": "Function size",
        "section": "function_size",
        "keys": ["target", "alert", "blocking"],
    },
    {
        "bullet": "Cyclomatic complexity",
        "section": "cyclomatic_complexity",
        "keys": ["target", "alert", "blocking"],
    },
]


def find_bullet(agents_md: str, bullet: str) -> str | None:
    """Return the AGENTS.md line declaring `bullet`, or None."""
    pattern = re.compile(r"^\s*[-*]\s*\*\*" + re.escape(bullet) + r"\*\*\s*:(.*)$",
                         re.IGNORECASE | re.MULTILINE)
    match = pattern.search(agents_md)
    return match.group(1) if match else None


def declared_numbers(line: str) -> list[int]:
    """Extract the thresholds declared on a bullet line, in order.

    Only integers attached to a comparison marker count: `>500`, `≤50`, `<=10`.
    A bare number in prose ("never keep adding 2 more") must not be picked up.
    """
    return [int(n) for n in re.findall(r"(?:[><]=?|≤|≥)\s*(\d+)", line)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-root", type=Path,
                        default=Path(__file__).resolve().parent.parent,
                        help="Stack root holding AGENTS.md and conventions.json")
    args = parser.parse_args()

    agents_path = args.stack_root / "AGENTS.md"
    conv_path = args.stack_root / "conventions.json"

    for path in (agents_path, conv_path):
        if not path.is_file():
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 1

    agents_md = agents_path.read_text(encoding="utf-8")
    conventions = json.loads(conv_path.read_text(encoding="utf-8"))

    errors: list[str] = []

    for rule in RULES:
        line = find_bullet(agents_md, rule["bullet"])
        if line is None:
            errors.append(f"AGENTS.md: no bullet found for '**{rule['bullet']}**:'")
            continue

        declared = declared_numbers(line)
        section = conventions.get(rule["section"])
        if not isinstance(section, dict):
            errors.append(f"conventions.json: missing section '{rule['section']}'")
            continue

        enforced = [section.get(k) for k in rule["keys"]]

        if None in enforced:
            missing = [k for k, v in zip(rule["keys"], enforced) if v is None]
            errors.append(f"conventions.json > {rule['section']}: missing key(s) {missing}")
            continue

        if declared != enforced:
            errors.append(
                f"'{rule['bullet']}' drifted:\n"
                f"    AGENTS.md declares   {declared}\n"
                f"    conventions.json has {enforced}  (keys: {rule['keys']})"
            )
        else:
            print(f"OK: {rule['bullet']} -> {enforced}")

    if errors:
        print("\nCONVENTION DRIFT DETECTED\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nFix AGENTS.md or conventions.json so both declare the same "
              "thresholds, then re-run.", file=sys.stderr)
        return 1

    print("\nAGENTS.md and conventions.json agree on every threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
