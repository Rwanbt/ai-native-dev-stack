#!/usr/bin/env python3
"""No machine-specific path may ship.

A public repository that contains `C:\\Users\\<someone>` in a distributed file
ships that someone's home directory to every clone, and a test that only runs
on that machine. The Anti-Debt adapters were committed once with the Mavis
daemon's absolute paths, and the enforcement script carried the maintainer's
defaults; neither is a contract a stranger can satisfy.

The gate scans every tracked text file and refuses the shapes that cannot be
portable: a Windows user profile, a macOS user home, a Linux home, a Documents
directory, or the maintainer's local account name. Two allowlists exist and
each entry states its reason:

* whole files - historical evidence whose bytes are the record (rewriting a
  qualification log to hide the interpreter path would falsify evidence);
* specific lines - documentation that demonstrates the forbidden pattern on
  purpose, or a placeholder like `/Users/you`.

Usage:
    python scripts/check_personal_paths.py            # verify (exit 1 on a hit)
    python scripts/check_personal_paths.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PATTERNS = (
    ("windows-profile", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+")),
    ("mac-home", re.compile(r"(?<![\w:/.])/Users/[A-Za-z0-9_.-]+")),
    ("linux-home", re.compile(r"(?<![\w:/.])/home/[A-Za-z0-9_.-]+")),
    ("documents-dir", re.compile(r"[A-Za-z]:[\\/]+Documents(?:[\\/]|$)")),
    ("local-account-in-path", re.compile(r"[\\/]barat(?:[\\/]|$)", re.IGNORECASE)),
)

# Files whose bytes are the historical record. Rewriting the path inside a
# qualification log would change evidence; the reason is the allowlist entry.
ALLOWED_FILES = {
    # The gate itself defines the forbidden patterns; its own source cannot be
    # expected to avoid quoting them.
    "scripts/check_personal_paths.py":
        "defines the forbidden shapes; the literals are regex sources, not paths",
    "tests/test_personal_paths_gate.py":
        "mutation fixtures: deliberately invalid paths the gate must refuse",
    "docs/qualification/claude-code.json":
        "historical qualification evidence: the interpreter path is part of the recorded run",
    "docs/qualification/codex-desktop.json":
        "historical qualification evidence: the interpreter path is part of the recorded run",
    "docs/qualification/opencode.json":
        "historical qualification evidence: the interpreter path is part of the recorded run",
    "docs/spikes/multivault/OBSIDIAN-GIT-BEHAVIOR-REPORT.md":
        "historical spike report executed on the maintainer's machine",
    "docs/spikes/multivault/SMART-CONNECTIONS-EGRESS-REPORT.md":
        "historical spike report executed on the maintainer's machine",
    "docs/spikes/multivault/SEMANTIC-RUNTIME-EVIDENCE-2026-09-11.json":
        "historical runtime evidence captured on the maintainer's machine",
    "docs/vault-v4-integration-agent-b-report.md":
        "historical integration report quoting the machine that ran it",
}

# Lines that deliberately demonstrate the forbidden shape or use the canonical
# placeholder. Marker = a substring of the line that must be present.
ALLOWED_LINES = {
    # The sentence that documents the absence of a hard-coded vault path.
    "README.md": ("There is no `D:\\Documents",),
    "README.fr.md": ("`D:\\Documents\\...`",),
    # The canonical placeholder for the macOS home directory.
    "tools/ai_docs/config.sh.example": ("/Users/you",),
    # A generic vault example, not a machine path.
    "scripts/vault_sync.ps1": ("MyVault",),
    # Authorship attribution, not a machine path.
    "routing-guide.md": ("Erwan Barat",),
}

SKIP_SUFFIXES = (".png", ".zip", ".whl", ".gz", ".ico", ".jpg", ".gif")


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return [name for name in out.splitlines() if name and not name.endswith(SKIP_SUFFIXES)]


def scan(root: Path, files: list[str] | None = None) -> list[dict]:
    """Every violation, as (file, line number, pattern, excerpt).

    `files` lets the mutation test feed a scratch tree; production always
    scans what Git tracks.
    """

    violations: list[dict] = []
    for name in (files if files is not None else tracked_files(root)):
        if name in ALLOWED_FILES:
            continue
        path = root / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        markers = ALLOWED_LINES.get(name, ())
        for number, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in markers):
                continue
            for label, pattern in PATTERNS:
                match = pattern.search(line)
                if match:
                    violations.append({"file": name, "line": number, "pattern": label,
                                       "match": match.group(0),
                                       "excerpt": line.strip()[:140]})
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO)
    args = parser.parse_args()

    violations = scan(Path(args.root))
    if args.json:
        print(json.dumps({"violations": violations, "passed": not violations},
                         indent=2, sort_keys=True))
    elif violations:
        print(f"MACHINE_PATH_VIOLATION: {len(violations)} hit(s)", file=sys.stderr)
        for item in violations:
            print(f"  {item['file']}:{item['line']} [{item['pattern']}] "
                  f"{item['match']}", file=sys.stderr)
    else:
        print("no machine-specific paths in tracked files")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())