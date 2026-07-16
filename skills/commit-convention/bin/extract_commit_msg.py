#!/usr/bin/env python3
"""
extract_commit_msg.py — Extract the commit message from a git commit command line.

Usage:
    echo "<git command>" | python3 extract_commit_msg.py

Reads the command from stdin, prints the commit message (or empty string).
Handles:
  - -F <file>
  - -m "..." / -m'...' / -m<token>  (multiple -m are joined by newlines)
  - --message=...

Fails soft (prints empty string) on any extraction error.
"""

import sys
import re


def extract(cmd):
    # -F <file>
    m = re.search(r'-F\s+(\S+)', cmd)
    if m:
        try:
            return open(m.group(1), 'r', encoding='utf-8').read()
        except Exception:
            pass

    # -m "..." / -m'...' / -m<token>  (collect ALL — body/footer paragraphs)
    parts = re.findall(
        r'''-m\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|(\S+))''',
        cmd,
    )
    if parts:
        out = []
        for triple in parts:
            s = next((x for x in triple if x is not None), '')
            out.append(s.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'"))
        return '\n'.join(out)

    # --message=...
    m = re.search(
        r'''--message\s*=\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|(\S+))''',
        cmd,
    )
    if m:
        s = next((x for x in m.groups() if x is not None), '')
        return s.replace('\\n', '\n')

    return ''


def hint(first_line):
    return f"""Commit message does not follow Conventional Commits 1.0.

First line: "{first_line}"

Expected: <type>[(<scope>)][!]: <subject>
  - type:    feat, fix, refactor, perf, docs, test, chore, build, ci, style, revert
  - scope:   optional, lowercase kebab-case, max 20 chars
  - subject: imperative, lowercase, no trailing period, max 72 chars
  - full first line: max 100 chars (else GitHub truncates)

Examples:
  feat(auth): add OAuth login
  fix(dsp-eq): prevent denormal flush
  feat(api)!: drop v1 endpoints

Or retry with --no-verify if the non-conformant message is intentional."""


def emit(decision, reason):
    import json
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))


def main():
    cmd = sys.stdin.read()
    mode = sys.argv[1] if len(sys.argv) > 1 else 'extract'

    if mode == 'extract':
        sys.stdout.write(extract(cmd))
    elif mode == 'hint':
        first = sys.argv[2] if len(sys.argv) > 2 else ''
        sys.stdout.write(hint(first))
    else:
        sys.stderr.write(f"unknown mode: {mode}\n")
        sys.exit(2)


if __name__ == '__main__':
    main()