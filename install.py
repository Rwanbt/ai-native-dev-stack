#!/usr/bin/env python3
"""install.py — bootstrap entry point for the AI-Native Dev Stack.

The lifecycle manager is the single authority for installing, switching,
uninstalling and updating a project (ADR-0009). This script exists for the one
situation it cannot cover: a fresh machine where `pip install` has not been run
and `ainative` is not on PATH. It resolves the lifecycle CLI from this checkout
and hands over.

    python install.py                             # asks which profile
    python install.py --profile standard
    python install.py --profile verified --dry-run

Everything afterwards goes through the installed CLI:

    ainative status
    ainative profile switch verified
    ainative update check
    ainative uninstall

Two things this script still owns, because neither is part of a project's
lifecycle state:

  * the optional gstack clone — third-party global skills, opt-in, pinned;
  * nothing else. The global multi-agent setup (harness instruction files,
    machine-wide skill links) is `scripts/install_agents.py`.

The pre-lifecycle flags (`--project-root`, `--skip-gstack`) still work, so a
script written against the old installer keeps running.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

STACK_ROOT = Path(__file__).resolve().parent

GSTACK_URL = "https://github.com/garrytan/gstack.git"

# gstack publishes no git tags — versions live only in commit messages, and the
# default branch moves daily. Tracking it means two students installing a week
# apart get different environments, which is unusable for teaching.
#
# So the default is a commit that was cloned and inspected before being written
# here (setup script present, 61 SKILL.md files, self-described v1.71.0.0).
# Override with --gstack-ref, or pass 'main' to track the default branch.
GSTACK_DEFAULT_REF = "394db326f2d3"  # v1.71.0.0 — verified 2026-08-27


def install_gstack(project: Path, choice: str, ref: str | None, dry_run: bool) -> None:
    """Clone gstack into the user's global skills directory. Opt-in, always."""

    target = Path.home() / ".claude" / "skills" / "gstack"
    if target.exists():
        print(f"gstack: already installed at {target} — skipping")
        return
    if choice != "yes":
        print("gstack: skipped (third-party code). Re-run with --with-gstack to install it.")
        return
    if not shutil.which("git"):
        print("gstack: WARNING — git not found, cannot install", file=sys.stderr)
        return
    if dry_run:
        print(f"gstack: would clone {GSTACK_URL} -> {target}")
        return

    print(f"gstack: cloning {GSTACK_URL} ...")
    try:
        subprocess.run(["git", "clone", GSTACK_URL, str(target)],
                       check=True, capture_output=True, text=True)
        if ref:
            subprocess.run(["git", "-C", str(target), "checkout", "--quiet", ref],
                           check=True, capture_output=True, text=True)
        sha = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        print(f"gstack: WARNING — install failed: {detail}", file=sys.stderr)
        return

    record_lock(project, "gstack", {"url": GSTACK_URL, "ref": ref or "default-branch",
                                    "commit": sha})
    print(f"gstack: installed at commit {sha[:12]} — recorded in .stack-lock.json")


def record_lock(project: Path, name: str, entry: dict) -> None:
    """Record what was actually installed, so a re-install is reproducible."""

    path = project / ".stack-lock.json"
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            print("WARNING: .stack-lock.json is malformed — rewriting it", file=sys.stderr)
    data.setdefault("tools", {})[name] = entry
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=("standard", "verified"), default=None,
                        help="install this profile without asking")
    parser.add_argument("--project", "--project-root", dest="project", type=Path,
                        default=Path.cwd(),
                        help="project root (--project-root is the pre-lifecycle name)")
    parser.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    gstack = parser.add_mutually_exclusive_group()
    gstack.add_argument("--with-gstack", dest="gstack", action="store_const", const="yes",
                        help="also install gstack (third-party code from GitHub)")
    gstack.add_argument("--skip-gstack", dest="gstack", action="store_const", const="no")
    parser.add_argument("--gstack-ref", default=GSTACK_DEFAULT_REF,
                        help=f"commit to pin gstack to (default: {GSTACK_DEFAULT_REF})")
    parser.set_defaults(gstack="no")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    project = args.project.resolve()

    if str(STACK_ROOT) not in sys.path:
        sys.path.insert(0, str(STACK_ROOT))
    try:
        from ainative.cli import main as lifecycle_main
    except ImportError as error:  # pragma: no cover - a broken checkout
        print(f"ERROR: cannot load the lifecycle CLI from {STACK_ROOT}: {error}",
              file=sys.stderr)
        return 2

    print("AI-Native Dev Stack — installer")
    print(f"Source:  {STACK_ROOT}")
    print(f"Project: {project}")
    print("(this is a bootstrap; `ainative` is the CLI from here on)\n")

    # Everything the old installer copied — tooling, skills, AGENTS.md,
    # config.sh, the .gitignore entry — is now a declared component with
    # recorded ownership, so it can be updated and removed as well as written.
    forwarded = ["init", "--project", str(project)]
    if args.profile:
        forwarded += ["--profile", args.profile]
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.json:
        forwarded.append("--json")

    status = lifecycle_main(forwarded)
    if status != 0:
        return status

    # gstack is third-party code executed by your agent: opt-in, never a timed
    # prompt that defaults to yes when nobody is looking at the screen.
    install_gstack(project, args.gstack, args.gstack_ref, args.dry_run)

    print("""
NEXT STEPS

1. Reference AGENTS.md from your agent's global config (one line, never a copy):
     Claude Code   ~/.claude/CLAUDE.md          -> @<project>/AGENTS.md
     OpenCode      ~/.config/opencode/AGENTS.md
     Codex         ~/.codex/AGENTS.md

2. Edit tools/ai_docs/config.sh (Obsidian vault, graphify binary, memory key).

3. Register the PostToolUse hook — see .ai-native/templates/settings_hook_example.json.

4. Write AI_CONTEXT.md per module — see .ai-native/templates/AI_CONTEXT_template.md.

5. Global multi-agent setup (once per machine):
     bash scripts/setup-agents.sh          (Linux / macOS / Git Bash)
     pwsh -File scripts/setup-agents.ps1   (Windows)

6. From now on:  ainative status | ainative profile switch <p> | ainative update
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
