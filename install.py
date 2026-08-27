#!/usr/bin/env python3
"""install.py — Set up the AI-Native Dev Stack in an existing project.

One cross-platform implementation: Linux, macOS and Windows, with or without
a POSIX shell. `install.sh` is a thin shim that delegates here.

What this does (per-project AI-docs stack):
  1. Copies tooling to tools/ai_docs/
  2. Installs the first-party skills into every detected agent root
  3. Copies AGENTS.md (the canonical engineering method) to the project root
  4. Installs gstack (third-party global skills) — opt-in, pinned
  5. Creates config.sh from the template
  6. Detects Python and validates it works
  7. Generates all AI_SUMMARY.md files

The GLOBAL, multi-agent setup lives in scripts/install_agents.py
(`bash scripts/setup-agents.sh` / `pwsh scripts/setup-agents.ps1`).

Usage:
    python install.py [--project-root PATH] [--with-gstack | --skip-gstack]
                      [--gstack-ref REF] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

STACK_ROOT = Path(__file__).resolve().parent

AI_DOCS_FILES = [
    "source_config.py",
    "module_discovery.py",
    "generate_ai_summary.py",
    "update_on_edit.py",
    "generate_all.py",
    "generate_metrics.py",
    "assemble_context.py",
    "run_hook.sh",
    "find_python.sh",
    "config.sh.example",
]

def first_party_skills() -> list[Path]:
    """Every skills/*/SKILL.md in the stack, discovered rather than listed.

    A hardcoded list silently stops shipping a skill the day one is added —
    the same drift this stack exists to prevent.
    """
    return sorted(p.parent for p in (STACK_ROOT / "skills").glob("*/SKILL.md"))

# Per-project skill roots, by CLI. `.agents/skills` is the cross-CLI convention
# used by Codex, OpenCode and recent Cursor; Claude Code keeps its own tree.
# Hardcoding only `.claude/skills` is why an OpenCode user used to get skills
# installed into a directory their CLI never reads.
PROJECT_SKILL_ROOTS = [
    (".claude/skills", "Claude Code"),
    (".agents/skills", "Codex / OpenCode / Cursor"),
]

GSTACK_URL = "https://github.com/garrytan/gstack.git"


class Installer:
    def __init__(self, project_root: Path, dry_run: bool) -> None:
        self.project = project_root.resolve()
        self.dry_run = dry_run
        self.warnings: list[str] = []

    # --- primitives -------------------------------------------------------

    def step(self, number: int, total: int, title: str) -> None:
        print(f"\n[{number}/{total}] {title}")

    def info(self, message: str) -> None:
        print(f"   {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"   WARNING: {message}")

    def mkdir(self, path: Path) -> None:
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def copy(self, source: Path, target: Path) -> bool:
        if not source.is_file():
            return False
        self.mkdir(target.parent)
        if not self.dry_run:
            shutil.copy2(source, target)
        return True

    def copy_tree(self, source: Path, target: Path) -> None:
        """Mirror a stack-owned directory into the project.

        Prunes files the source no longer has. A plain copy leaves a file
        deleted upstream sitting in every project that installed it earlier —
        the same silent drift this stack exists to prevent. These directories
        are entirely stack-managed, so nothing user-authored is at risk.
        """
        if not source.is_dir():
            return
        self.mkdir(target)

        wanted: set[Path] = set()
        for item in source.rglob("*"):
            if item.is_dir():
                continue
            relative = item.relative_to(source)
            wanted.add(relative)
            self.copy(item, target / relative)

        if not target.is_dir():
            return
        for existing in sorted(target.rglob("*"), reverse=True):
            if existing.is_dir():
                if not any(existing.iterdir()) and not self.dry_run:
                    existing.rmdir()
                continue
            if existing.relative_to(target) not in wanted:
                self.info(f"pruned {existing.relative_to(self.project)} (removed upstream)")
                if not self.dry_run:
                    existing.unlink()

    # --- steps ------------------------------------------------------------

    def copy_ai_docs(self) -> None:
        self.step(1, 7, "Copying tooling to tools/ai_docs/ ...")
        destination = self.project / "tools" / "ai_docs"
        copied = sum(
            self.copy(STACK_ROOT / "tools" / "ai_docs" / name, destination / name)
            for name in AI_DOCS_FILES
        )
        hook = destination / "run_hook.sh"
        if hook.is_file() and os.name != "nt":
            hook.chmod(hook.stat().st_mode | 0o111)
        self.info(f"OK ({copied} files)")

    def install_skills(self) -> None:
        self.step(2, 7, "Installing first-party skills into every agent root ...")
        skills = first_party_skills()
        if not skills:
            self.warn("no skills found under the stack's skills/ directory")
            return
        for relative_root, label in PROJECT_SKILL_ROOTS:
            root = self.project / relative_root
            for source in skills:
                self.copy_tree(source, root / source.name)
            validator = root / "commit-convention" / "bin" / "validate-commit.sh"
            if validator.is_file() and os.name != "nt":
                validator.chmod(validator.stat().st_mode | 0o111)
            names = ", ".join(s.name for s in skills)
            self.info(f"{relative_root:<18} <- {len(skills)} skills  ({label})")
            self.info(f"{'':<18}    {names}")

    def copy_agents_md(self) -> None:
        self.step(3, 7, "Copying AGENTS.md (cross-tool universal rules) ...")
        target = self.project / "AGENTS.md"
        if target.exists():
            self.info("SKIP — AGENTS.md already exists (not overwriting)")
            return
        self.copy(STACK_ROOT / "AGENTS.md", target)
        self.info("Created AGENTS.md — reference it from your agent's global config")

        conventions = self.project / "conventions.json"
        if not conventions.exists():
            self.copy(STACK_ROOT / "conventions.json", conventions)
            self.info("Created conventions.json — machine-readable thresholds")

    def install_gstack(self, choice: str, ref: str | None) -> None:
        self.step(4, 7, "gstack — third-party global skills (github.com/garrytan/gstack)")
        target = Path.home() / ".claude" / "skills" / "gstack"

        if target.exists():
            self.info(f"ALREADY INSTALLED at {target} — skipping")
            return
        if choice != "yes":
            self.info("Skipped. Re-run with --with-gstack to install it.")
            return
        if not shutil.which("git"):
            self.warn("git not found — cannot install gstack")
            return
        if self.dry_run:
            self.info(f"would clone {GSTACK_URL} -> {target}")
            return

        self.info(f"Cloning {GSTACK_URL} ...")
        try:
            subprocess.run(["git", "clone", GSTACK_URL, str(target)],
                           check=True, capture_output=True, text=True)
            if ref:
                subprocess.run(["git", "-C", str(target), "checkout", "--quiet", ref],
                               check=True, capture_output=True, text=True)
            sha = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                                 check=True, capture_output=True, text=True).stdout.strip()
        except subprocess.CalledProcessError as err:
            self.warn(f"gstack install failed: {(err.stderr or err.stdout or '').strip()}")
            return

        self.record_lock("gstack", {"url": GSTACK_URL, "ref": ref or "default-branch",
                                    "commit": sha})
        self.info(f"Installed at commit {sha[:12]} — recorded in .stack-lock.json")
        self.info("Re-run with --gstack-ref <commit> to reproduce this exact version.")

    def record_lock(self, name: str, entry: dict) -> None:
        """Record what was actually installed, so a re-install is reproducible."""
        lock_path = self.project / ".stack-lock.json"
        data: dict = {}
        if lock_path.is_file():
            try:
                data = json.loads(lock_path.read_text(encoding="utf-8"))
            except ValueError:
                self.warn(".stack-lock.json is malformed — rewriting it")
        data.setdefault("tools", {})[name] = entry
        if not self.dry_run:
            lock_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def create_config(self) -> None:
        self.step(5, 7, "Creating tools/ai_docs/config.sh ...")
        config = self.project / "tools" / "ai_docs" / "config.sh"
        if config.exists():
            self.info("SKIP — config.sh already exists (not overwriting)")
            return
        self.copy(STACK_ROOT / "tools" / "ai_docs" / "config.sh.example", config)
        self.info("Created config.sh — set your Obsidian vault path and graphify binary")

    def detect_python(self) -> str | None:
        self.step(6, 7, "Detecting Python ...")
        for candidate in (sys.executable, "python3", "python", "py"):
            if not candidate:
                continue
            try:
                out = subprocess.run(
                    [candidate, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                    capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                continue
            if out.returncode == 0:
                version = out.stdout.strip()
                if tuple(int(p) for p in version.split(".")[:2]) >= (3, 8):
                    self.info(f"Found: {candidate} ({version})")
                    return candidate
        self.warn("No Python 3.8+ found — set PYTHON_BIN in tools/ai_docs/config.sh")
        return None

    def generate_summaries(self, python: str | None) -> None:
        self.step(7, 7, "Generating AI_SUMMARY.md ...")
        if python is None:
            self.info("SKIP — Python not found")
            return
        contexts = [p for p in self.project.rglob("AI_CONTEXT.md")
                    if ".git" not in p.parts and "node_modules" not in p.parts]
        if not contexts:
            self.info("SKIP — no AI_CONTEXT.md files yet.")
            self.info("Create one per module from templates/AI_CONTEXT_template.md, then run:")
            self.info("   python tools/ai_docs/generate_all.py")
            return
        if self.dry_run:
            self.info(f"would generate summaries for {len(contexts)} module(s)")
            return
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        subprocess.run([python, "tools/ai_docs/generate_all.py"],
                       cwd=self.project, env=env, check=False)

    def update_gitignore(self) -> None:
        gitignore = self.project / ".gitignore"
        existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
        if "tools/ai_docs/config.sh" in existing:
            return
        if self.dry_run:
            return
        with gitignore.open("a", encoding="utf-8") as handle:
            handle.write("\n# AI docs stack — machine-specific config (never commit)\n")
            handle.write("tools/ai_docs/config.sh\n")
        print("\n   Added config.sh to .gitignore")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    gstack = parser.add_mutually_exclusive_group()
    gstack.add_argument("--with-gstack", dest="gstack", action="store_const", const="yes",
                        help="install gstack (third-party code from GitHub)")
    gstack.add_argument("--skip-gstack", dest="gstack", action="store_const", const="no")
    parser.add_argument("--gstack-ref", default=None,
                        help="commit or tag to pin gstack to (reproducible installs)")
    parser.add_argument("--dry-run", action="store_true", help="show actions, change nothing")
    parser.set_defaults(gstack="no")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project_root.resolve()

    print("\nAI-Native Dev Stack — Installer")
    print("=" * 32)
    print(f"Source:  {STACK_ROOT}")
    print(f"Project: {project}")
    if args.dry_run:
        print("(dry-run — nothing will be written)")

    if not (project / ".git").exists():
        print(f"\nERROR: {project} is not a git repository.", file=sys.stderr)
        return 1

    installer = Installer(project, args.dry_run)
    installer.copy_ai_docs()
    installer.install_skills()
    installer.copy_agents_md()
    # gstack is third-party code executed by your agent: opt-in, never a
    # timed prompt that defaults to yes when nobody is looking at the screen.
    installer.install_gstack(args.gstack, args.gstack_ref)
    installer.create_config()
    python = installer.detect_python()
    installer.generate_summaries(python)
    installer.update_gitignore()

    print("\n" + "=" * 52)
    print("  INSTALL COMPLETE" + ("  (dry-run)" if args.dry_run else ""))
    print("=" * 52)
    if installer.warnings:
        print(f"\n{len(installer.warnings)} warning(s):")
        for warning in installer.warnings:
            print(f"  - {warning}")

    print("""
NEXT STEPS:

1. Reference AGENTS.md from your agent's global config (one line, never a copy):
     Claude Code   ~/.claude/CLAUDE.md          -> @<project>/AGENTS.md
     OpenCode      ~/.config/opencode/AGENTS.md
     Codex         ~/.codex/AGENTS.md

2. Edit tools/ai_docs/config.sh (Obsidian vault, graphify binary, memory key).

3. Register the PostToolUse hook — see templates/settings_hook_example.json.

4. Write AI_CONTEXT.md per module — see templates/AI_CONTEXT_template.md.

5. Verify:  /verify-ai-docs

6. Global multi-agent setup (once per machine):
     bash scripts/setup-agents.sh          (Linux / macOS / Git Bash)
     pwsh -File scripts/setup-agents.ps1   (Windows)
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
