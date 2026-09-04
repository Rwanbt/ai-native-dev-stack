#!/usr/bin/env python3
"""Clean-install end-to-end: build a wheel, install it as a user, then use it.

Every other lifecycle test imports the package from the checkout. This one does
not: it builds the wheel, installs it into a throwaway virtual environment, and
drives the `ainative` console script from a directory that has never heard of
this repository — no `PYTHONPATH`, no developer venv, no pre-existing config.

It is the only gate that catches a lifecycle layer which works from inside its
own source tree and nowhere else, and the only one that proves the staged
payload in the wheel installs the same files a checkout does.

Usage:
    python scripts/lifecycle_clean_install.py
    python scripts/lifecycle_clean_install.py --keep     # leave the venv for inspection
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STEP_TIMEOUT_SECONDS = 900

# Paths that legitimately differ between two installs of the same profile: the
# state carries an installation id and timestamps, and the journal and backups
# are per-transaction.
VOLATILE = (".ai-native/lifecycle/state.json",
            ".ai-native/lifecycle/transactions",
            ".ai-native/lifecycle/backups")


class Failure(SystemExit):
    pass


def run(command: list[str], *, cwd: Path | None = None, env: dict | None = None,
        expect: int = 0) -> subprocess.CompletedProcess:
    completed = subprocess.run([str(item) for item in command], cwd=str(cwd) if cwd else None,
                               env=env, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=STEP_TIMEOUT_SECONDS)
    print(f"  $ {' '.join(str(i) for i in command[-5:])}  -> {completed.returncode}")
    if completed.returncode != expect:
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:], file=sys.stderr)
        raise Failure(f"expected exit {expect}, got {completed.returncode}: {command}")
    return completed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(f"FAILED: {message}")


def tree(base: Path) -> set[str]:
    return {path.relative_to(base).as_posix() for path in base.rglob("*")
            if path.is_file()
            and not any(path.relative_to(base).as_posix().startswith(v) for v in VOLATILE)}


def clean_environment() -> dict:
    """Nothing that could point the CLI back at this checkout."""

    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "AINATIVE_STACK_SOURCE", "AINATIVE_UPDATE_PROVIDER",
                          "AINATIVE_UPDATE_LOCAL_DIR", "AINATIVE_UPDATE_URL")}
    env["AINATIVE_NO_UPDATE_CHECK"] = "1"   # an E2E must not depend on a network
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def build_and_install(root: Path) -> tuple[Path, Path]:
    print("[1] build the wheel and install it into a fresh venv")
    distribution = root / "dist"
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q",
         "build"])
    run([sys.executable, "-m", "build", "--wheel", "--outdir", distribution], cwd=REPO)
    wheel = next(distribution.glob("*.whl"))
    print(f"      wheel: {wheel.name}")

    venv = root / "venv"
    run([sys.executable, "-m", "venv", venv])
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    ainative = scripts / ("ainative.exe" if os.name == "nt" else "ainative")
    run([python, "-m", "pip", "install", "--disable-pip-version-check", "-q", wheel])
    require(ainative.exists(), f"the console entry point was not installed at {ainative}")
    return ainative, venv


def check_versions(ainative: Path, cwd: Path, env: dict) -> None:
    print("[2] the CLI reports its versions without needing the checkout")
    output = run([ainative, "--version"], cwd=cwd, env=env).stdout
    for label in ("lifecycle:", "state_schema:", "stack:", "workplane_runtime:"):
        require(label in output, f"`--version` did not report {label}")
    require("no distribution source" not in output,
            "the installed wheel carries no payload — a user with no checkout "
            "cannot install anything")


def check_install(ainative: Path, project: Path, cwd: Path, env: dict) -> None:
    print("[3] dry run writes nothing; install writes the profile")
    run([ainative, "init", "--profile", "standard", "--project", project, "--dry-run"],
        cwd=cwd, env=env)
    require(not (project / "AGENTS.md").exists(), "a dry run wrote to the project")

    run([ainative, "init", "--profile", "standard", "--project", project], cwd=cwd, env=env)
    for marker in ("AGENTS.md", "conventions.json", "tools/ai_docs/generate_all.py",
                   ".claude/skills/verify-ai-docs/SKILL.md",
                   ".agents/skills/verify-ai-docs/SKILL.md",
                   ".ai-native/lifecycle/state.json"):
        require((project / marker).is_file(), f"missing after a Standard install: {marker}")


def check_payload_matches_checkout(ainative: Path, project: Path, root: Path,
                                   cwd: Path, env: dict) -> None:
    print("[4] the wheel's staged payload installs exactly what the checkout does")
    mirror = root / "from-checkout"
    mirror.mkdir()
    run([ainative, "init", "--profile", "standard", "--project", mirror],
        cwd=cwd, env={**env, "AINATIVE_STACK_SOURCE": str(REPO)})

    from_payload = tree(project) - {"NOTES.md", "src/app.py"}
    from_checkout = tree(mirror)
    difference = from_payload.symmetric_difference(from_checkout)
    require(not difference,
            "a payload install and a checkout install differ: " + ", ".join(sorted(difference)))
    print(f"      {len(from_payload)} files, identical sets")


def check_round_trip(ainative: Path, project: Path, cwd: Path, env: dict) -> None:
    print("[5] standard -> verified -> standard -> verified, history intact")
    run([ainative, "profile", "switch", "verified", "--project", project], cwd=cwd, env=env)
    require((project / ".ai-native/lifecycle/verified.json").is_file(),
            "the Verified marker was not written")

    work = project / ".ai-native" / "work" / "w1"
    work.mkdir(parents=True)
    (work / "manifest.json").write_text('{"revision":1}', encoding="utf-8")

    run([ainative, "profile", "switch", "standard", "--project", project], cwd=cwd, env=env)
    require((work / "manifest.json").is_file(), "the downgrade destroyed the audit trail")
    require(not (project / ".ai-native/lifecycle/verified.json").exists(),
            "the Verified marker survived the downgrade")

    run([ainative, "profile", "switch", "verified", "--project", project], cwd=cwd, env=env)
    require((work / "manifest.json").is_file(), "the reactivation lost the audit trail")


def check_reporting(ainative: Path, project: Path, cwd: Path, env: dict) -> None:
    print("[6] status, doctor, and the Verified surface")
    run([ainative, "status", "--project", project], cwd=cwd, env=env)
    run([ainative, "status", "--json", "--project", project], cwd=cwd, env=env)
    run([ainative, "doctor", "--project", project], cwd=cwd, env=env)
    for command in ("trust", "work", "verify", "converge", "debug"):
        run([ainative, command, "--help"], cwd=cwd, env=env)


def check_non_interactive(ainative: Path, project: Path, cwd: Path, env: dict) -> None:
    print("[7] no command blocks on a prompt, and none acts without --yes")
    run([ainative, "init", "--project", project], cwd=cwd, env=env, expect=2)
    run([ainative, "uninstall", "--purge", "--project", project], cwd=cwd, env=env, expect=2)
    require((project / ".ai-native/work/w1/manifest.json").is_file(),
            "a refused purge deleted data anyway")


def check_uninstall(ainative: Path, project: Path, cwd: Path, env: dict) -> None:
    print("[8] uninstall keeps the user's work; purge removes only what we own")
    run([ainative, "uninstall", "--dry-run", "--project", project], cwd=cwd, env=env)
    run([ainative, "uninstall", "--project", project], cwd=cwd, env=env)
    require((project / "NOTES.md").is_file(), "an uninstall removed a user file")
    require((project / "src" / "app.py").is_file(), "an uninstall removed user source")
    require((project / ".ai-native/work/w1/manifest.json").is_file(),
            "an uninstall removed the audit trail")
    require(not (project / ".claude/skills/verify-ai-docs/SKILL.md").exists(),
            "an uninstall left an unmodified managed file behind")

    print("[9] reinstall, then purge")
    run([ainative, "init", "--profile", "verified", "--project", project], cwd=cwd, env=env)
    run([ainative, "uninstall", "--purge", "--yes", "--project", project], cwd=cwd, env=env)
    require(not (project / ".ai-native" / "work").exists(), "purge left Verified data")
    require((project / "NOTES.md").is_file(), "purge removed an unrelated user file")
    require((project / "src" / "app.py").is_file(), "purge removed user source")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", action="store_true", help="do not delete the workspace")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="ainative-clean-install-"))
    project = root / "fresh-project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (project / "NOTES.md").write_text("my own notes\n", encoding="utf-8")

    try:
        ainative, _ = build_and_install(root)
        env = clean_environment()
        check_versions(ainative, root, env)
        check_install(ainative, project, root, env)
        check_payload_matches_checkout(ainative, project, root, root, env)
        check_round_trip(ainative, project, root, env)
        check_reporting(ainative, project, root, env)
        check_non_interactive(ainative, project, root, env)
        check_uninstall(ainative, project, root, env)
    finally:
        if args.keep:
            print(f"\nworkspace kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)

    print("\nCLEAN INSTALL: all gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
