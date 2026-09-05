#!/usr/bin/env python3
"""Acceptance Criteria guard for issue-to-implementation.

The Acceptance Criteria of an Issue are canonically the checklist under an
"Acceptance criteria" heading in the Issue body (the generic templates ship
one). There is no separate AC database — the Issue body is the only home.

The canonical digest is content-addressed and checkbox-state independent:
ticking `- [ ]` to `- [x]` during implementation is progress, while editing a
criterion line is drift. Any canonical difference against the bound digest is
`ISSUE_CHANGED`. Whether a change is *material* is judged by the AC
protection policy (docs/GITHUB-WORKFLOW.md) by the agent and maintainer —
this guard only makes drift undeniably visible, fail-closed: when the AC
section disappears or cannot be extracted, that is drift too.

Usage:
    python ac_guard.py --bind           < issue-body.md
    # -> {"digest": "...", "criteria": ["...", ...]}        (exit 0)

    python ac_guard.py --check DIGEST   < issue-body.md
    # -> {"verdict": "OK"}                                   (exit 0)
    # -> {"verdict": "ISSUE_CHANGED", "reason": "..."}       (exit 1)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

# A heading at any level, "acceptance criteria", optional colon. Case does
# not matter; a trailing blank does not either.
_HEADING = re.compile(r"^ {0,3}#{1,6}\s*acceptance criteria\s*:?\s*$", re.MULTILINE | re.IGNORECASE)
# Checkbox items, checked or unchecked. State is stripped by the canonicalizer.
_ITEM = re.compile(r"^\s*[-*+]\s+\[[ xX ]\]\s+(.*)$")


def extract(body: str) -> list[str]:
    """The AC criterion lines, in order, checkbox marks and wrappings gone."""

    match = _HEADING.search(body or "")
    if match is None:
        return []
    rest = body[match.end():]
    next_heading = re.search(r"^#{1,6}\s+\S", rest, re.MULTILINE)
    section = rest[:next_heading.start()] if next_heading else rest
    criteria: list[str] = []
    for line in section.splitlines():
        item = _ITEM.match(line)
        if item:
            text = re.sub(r"\s+", " ", item.group(1)).strip()
            if text:
                criteria.append(text)
    return criteria


def canonical(body: str) -> str:
    return "\n".join(extract(body))


def digest(body: str) -> str:
    """sha256 of the canonical AC. Stable across checkbox state and CRLF."""

    return hashlib.sha256(canonical(body).replace("\r\n", "\n").encode("utf-8")).hexdigest()


def check(current_body: str, bound_digest: str) -> dict:
    """Compare the current AC digest with the bound one. Fail-closed."""

    current = digest(current_body)
    if not bound_digest:
        return {"verdict": "ISSUE_CHANGED",
                "reason": "no bound digest was recorded; bind one before merge"}
    if current != bound_digest:
        return {"verdict": "ISSUE_CHANGED",
                "reason": "current canonical AC digest differs from the bound digest"}
    return {"verdict": "OK", "digest": current}


def main(argv: list[str]) -> int:
    body = sys.stdin.read()
    if argv and argv[0] == "--bind":
        print(json.dumps({"digest": digest(body), "criteria": extract(body)}, indent=2))
        return 0
    if argv and argv[0] == "--check" and len(argv) == 2:
        verdict = check(body, argv[1])
        print(json.dumps(verdict, indent=2))
        return 0 if verdict["verdict"] == "OK" else 1
    print("usage: ac_guard.py (--bind | --check DIGEST) < issue-body.md", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))