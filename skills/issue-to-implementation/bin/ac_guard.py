#!/usr/bin/env python3
"""Acceptance Criteria guard for issue-to-implementation.

The Acceptance Criteria of an Issue are canonically the checklist under an
"Acceptance criteria" heading in the Issue body (the generic templates ship
one). There is no separate AC database — the Issue body is the only home.

The digest covers the COMPLETE semantic content of every criterion: its
checkbox line, the continuation lines indented or written beneath it, and
the nested bullets belonging to it. Flipping "never expose a stack trace"
into "include the stack trace" on a continuation line must produce
ISSUE_CHANGED — a digest that only saw the first physical line would bless
that edit.

Noise (never part of the contract): checkbox checked/unchecked state,
bullet marker style (`-`/`*`/`+`), CRLF vs LF, indentation amount,
template guidance in HTML comments, blank lines. Everything else —
criterion order, nested text, punctuation — is contract. Order is not
sorted: the sequence the maintainer wrote is the sequence the work is
held to.

Fail-closed contracts, pinned by tests/test_github_work_skills.py:

    bind(body)  -> {"digest", "criteria"}                        (valid AC)
                | {"verdict": "INVALID_ACCEPTANCE_CRITERIA"}     (no heading,
                                              or zero checkbox criteria)
    check(cur, bound) -> {"verdict": "OK"} | {"verdict": "ISSUE_CHANGED",
                                               "reason": ...}
    -- every non-OK case is ISSUE_CHANGED with a distinct reason:
       never silently OK.

Usage:
    python ac_guard.py --bind           < issue-body.md
    # -> {"digest": "...", "criteria": [...]}                (exit 0)
    # -> {"verdict": "INVALID_ACCEPTANCE_CRITERIA", ...}     (exit 1)

    python ac_guard.py --check DIGEST   < issue-body.md
    # -> {"verdict": "OK"}                                   (exit 0)
    # -> {"verdict": "ISSUE_CHANGED", "reason": "..."}       (exit 1)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys

# A heading at any level, "acceptance criteria", optional colon. Up to three
# spaces of indentation is CommonMark-legal for an ATX heading. Case does
# not matter; a trailing blank does not either.
_HEADING = re.compile(r"^ {0,3}#{1,6}\s*acceptance criteria\s*:?\s*$", re.MULTILINE | re.IGNORECASE)
_ANY_HEADING = re.compile(r"^ {0,3}#{1,6}\s+\S", re.MULTILINE)
# A top-level checkbox item starts a criterion; its state is noise.
_TOP_CHECKBOX = re.compile(r"^ {0,3}[-*+]\s+\[[ xX]\]\s*(.*)$")
# A nested checkbox inside a criterion: state is noise, content is contract.
_NESTED_CHECKBOX = re.compile(r"^ {1,}[-*+]\s+\[[ xX]\]\s*(.*)$")
# A nested bullet: style is noise (`*` renders like `-`), content is contract.
_BULLET = re.compile(r"^ {1,}[-*+]\s+(.*)$")
# Template guidance comments, single- or multi-line.
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

INVALID = "INVALID_ACCEPTANCE_CRITERIA"
OK = "OK"
CHANGED = "ISSUE_CHANGED"


def _normalize_line(line: str) -> str:
    text = line.strip()
    nested = _NESTED_CHECKBOX.match(text)
    if nested:
        text = "- " + nested.group(1).strip()
    else:
        bullet = _BULLET.match(text)
        if bullet:
            text = "- " + bullet.group(1).strip()
    return re.sub(r"\s+", " ", text)


def extract(body: str) -> list[str]:
    """The AC criteria, in order. Each criterion is its checkbox line plus
    every semantic line belonging to it (continuations, nested bullets),
    whitespace-normalized. Blank lines, template comments and checkbox
    state never reach the canonical form."""

    if not body:
        return []
    match = _HEADING.search(body)
    if match is None:
        return []
    rest = body[match.end():]
    next_heading = _ANY_HEADING.search(rest)
    section = rest[:next_heading.start()] if next_heading else rest
    section = _COMMENT.sub("", section)

    criteria: list[str] = []
    parts = None  # None until the first top-level checkbox
    for raw in section.splitlines():
        top = _TOP_CHECKBOX.match(raw)
        if top is not None:
            if parts is not None and any(parts):
                criteria.append(" ".join(parts))
            parts = []
            text = re.sub(r"\s+", " ", top.group(1)).strip()
            if text:
                parts.append(text)
            continue
        if parts is None or not raw.strip():
            continue  # preamble before the first checkbox, or structure
        normalized = _normalize_line(raw)
        if normalized:
            parts.append(normalized)
    if parts is not None and any(parts):
        criteria.append(" ".join(parts))
    return criteria


def canonical(body: str) -> str:
    return "\n".join(extract(body))


def digest(body: str) -> str:
    """sha256 of the canonical AC. Stable across checkbox state, bullet
    style, CRLF, indentation and template comments."""

    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def bind(body: str) -> dict:
    """The binding contract. Refuses to mint a digest for an Issue whose AC
    is absent or empty: the sha256 of an empty string is not a contract,
    and treating it as one would make every AC-less body 'bound'."""

    if _HEADING.search(body or "") is None:
        return {"verdict": INVALID,
                "reason": "no 'Acceptance criteria' heading found in the Issue body"}
    criteria = extract(body)
    if not criteria:
        return {"verdict": INVALID,
                "reason": "the 'Acceptance criteria' heading contains no checkbox criterion"}
    return {"digest": digest(body), "criteria": criteria}


def check(current_body: str, bound_digest: str) -> dict:
    """Compare the current AC against the bound one. Fail-closed: no bound
    digest, an unusable current AC, or any canonical difference is
    ISSUE_CHANGED — never a silent OK."""

    if not bound_digest:
        return {"verdict": CHANGED,
                "reason": "no bound digest was recorded; bind one before merge"}
    current = extract(current_body or "")
    if not current:
        return {"verdict": CHANGED,
                "reason": "the Issue no longer contains usable Acceptance Criteria"}
    if digest(current_body) != bound_digest:
        return {"verdict": CHANGED,
                "reason": "current canonical AC digest differs from the bound digest"}
    return {"verdict": OK, "digest": bound_digest}


def main(argv: list[str]) -> int:
    body = sys.stdin.read()
    if argv and argv[0] == "--bind":
        verdict = bind(body)
        print(json.dumps(verdict, indent=2))
        return 0 if "digest" in verdict else 1
    if argv and argv[0] == "--check" and len(argv) == 2:
        outcome = check(body, argv[1])
        print(json.dumps(outcome, indent=2))
        return 0 if outcome["verdict"] == OK else 1
    print("usage: ac_guard.py (--bind | --check DIGEST) < issue-body.md", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))