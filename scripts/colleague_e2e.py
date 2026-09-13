#!/usr/bin/env python3
"""The colleague run: the README, executed literally, against a real wheel.

A stranger has Python, Git and a network. This script builds the wheel (or
takes a published one), makes a fresh virtual environment and a fresh Git
project, installs the wheel there, and then uses only the commands the README
documents — no fixture from this repository, no hidden file, no PYTHONPATH.
If a step needs something the README does not give, this fails; that is the
property the script exists to test.

    python scripts/colleague_e2e.py                     # build then run
    python scripts/colleague_e2e.py --wheel path.whl    # published artifact run
    python scripts/colleague_e2e.py --keep              # keep the workspace
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKPOINTS: list[str] = []


class CheckFailed(RuntimeError):
    """One documented step did not work; the run stops and reports it."""


def check(label: str) -> None:
    CHECKPOINTS.append(label)
    print(f"[ok] {label}")


def fail(label: str, detail: str) -> None:
    raise CheckFailed(f"{label}: {detail}")


def run(argv: list[str], *, cwd: Path, env: dict | None = None,
        input_text: str | None = None, timeout: int = 600,
        shell_string: str | None = None) -> subprocess.CompletedProcess:
    """One subprocess with a full traceback-free contract.

    `shell_string` exists for exactly one caller: the configured hook entry is
    a shell command by design (`bash ...` or `powershell ... -File ...`), and
    the only faithful way to run it is the way the harness runs it ? through
    the platform shell. Everything else passes an argv list.
    """

    if shell_string is not None:
        completed = subprocess.run(
            shell_string, shell=True, cwd=str(cwd), env=env,
            capture_output=True, text=True, errors="replace",
            input=input_text, timeout=timeout)
        return completed
    completed = subprocess.run(
        [str(item) for item in argv], cwd=str(cwd), env=env,
        capture_output=True, text=True, errors="replace",
        input=input_text, stdin=None if input_text is not None else subprocess.DEVNULL,
        timeout=timeout)
    return completed


def user_env(venv_bin: Path) -> dict:
    """The environment a colleague has: no checkout on any path."""

    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "AINATIVE_STACK_SOURCE", "PYTHONHOME")}
    env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    for name in ("OBSIDIAN_VAULT", "OBSIDIAN_PROJECT_SLUG",
                 "AINATIVE_MULTIVAULT_GOVERNED"):
        env.pop(name, None)
    return env


def cli(ainative: Path, project: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    completed = run([ainative, *args], cwd=project, env=env)
    combined = completed.stdout + completed.stderr
    if "Traceback" in combined:
        fail(f"ainative {' '.join(args)}", f"traceback instead of a message:\n{combined[-1200:]}")
    return completed


def build_wheel(dist: Path) -> Path:
    print("[1] build the wheel")
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "-q", "build"], cwd=REPO)
    completed = run([sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
                    cwd=REPO)
    if completed.returncode != 0:
        fail("build the wheel", completed.stderr[-800:])
    wheel = next(dist.glob("*.whl"))
    check(f"wheel built: {wheel.name}")
    return wheel


def make_venv(root: Path, wheel: Path) -> tuple[Path, Path, Path]:
    print("[2] fresh virtual environment, wheel installed")
    venv = root / "venv"
    completed = run([sys.executable, "-m", "venv", str(venv)], cwd=root)
    if completed.returncode != 0:
        fail("create the venv", completed.stderr[-500:])
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    completed = run([python, "-m", "pip", "install", "--disable-pip-version-check",
                     "-q", str(wheel)], cwd=root)
    if completed.returncode != 0:
        fail("install the wheel", completed.stderr[-800:])
    ainative = bin_dir / ("ainative.exe" if os.name == "nt" else "ainative")
    if not ainative.is_file():
        fail("the console script", f"{ainative} was not installed")
    check(f"installed {wheel.name} into a fresh venv")
    return python, ainative, bin_dir

def run_documented_flow(venv_python: Path, ainative: Path, project: Path,
                        env: dict) -> None:
    """Exactly what the README tells a colleague to run, in order."""

    print("[3] the documented flow, in a fresh Git project")
    completed = run(["git", "init", "-q", "."], cwd=project, env=env)
    if completed.returncode != 0:
        fail("git init", completed.stderr[-300:])
    run(["git", "-C", str(project), "config", "user.email", "colleague@example.com"],
        cwd=project, env=env)
    run(["git", "-C", str(project), "config", "user.name", "Colleague"], cwd=project, env=env)
    (project / "README.md").write_text("# my project\n", encoding="utf-8")
    run(["git", "-C", str(project), "add", "-A"], cwd=project, env=env)
    run(["git", "-C", str(project), "commit", "-qm", "init"], cwd=project, env=env)

    version = cli(ainative, project, env, "--version")
    if version.returncode != 0:
        fail("ainative --version", version.stderr[-400:])
    check("ainative --version answers")

    provenance = run([venv_python, "-c",
                      "import ainative, sys; print(ainative.__file__)"],
                     cwd=project, env=env)
    package_file = provenance.stdout.strip()
    if not package_file or str(project) in package_file or "site-packages" not in package_file:
        fail("package provenance",
             f"imported ainative from {package_file!r}, not from the installed wheel")
    check(f"imports from site-packages: {Path(package_file).name}")

    init = cli(ainative, project, env, "init", "--profile", "standard")
    if init.returncode != 0:
        fail("ainative init --profile standard", init.stdout[-600:] + init.stderr[-600:])
    if not (project / ".ai-native" / "lifecycle" / "state.json").is_file():
        fail("init", "no lifecycle state was written")
    if not (project / ".claude" / "settings.json").is_file():
        fail("init", "no PostToolUse hook configuration was written")
    check("ainative init --profile standard installs the project")

    status = cli(ainative, project, env, "status")
    if status.returncode != 0:
        fail("ainative status", status.stdout[-600:])
    check("ainative status reports a healthy install")

    doctor = cli(ainative, project, env, "doctor")
    if doctor.returncode != 0:
        fail("ainative doctor", doctor.stdout[-800:] + doctor.stderr[-400:])
    check("ainative doctor is green")

    knowledge = cli(ainative, project, env, "knowledge", "status")
    if knowledge.returncode != 0:
        fail("ainative knowledge status", knowledge.stdout[-600:])
    check("ainative knowledge status answers")

    context = cli(ainative, project, env, "context", "status")
    if context.returncode != 0:
        fail("ainative context status", context.stdout[-600:])
    check("ainative context status answers")

    # README steps 4-5: declare a module with its AI_CONTEXT.md (from the
    # shipped template) and generate the summaries once.
    source_dir = project / "src"
    source_dir.mkdir()
    template = project / ".ai-native" / "templates" / "AI_CONTEXT_template.md"
    if not template.is_file():
        fail("the AI_CONTEXT template", f"{template} was not installed")
    (source_dir / "AI_CONTEXT.md").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8")
    source = source_dir / "main.py"
    source.write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")
    generated = run([venv_python, "tools/ai_docs/generate_all.py"], cwd=project, env=env)
    summary = source_dir / "AI_SUMMARY.md"
    if generated.returncode != 0 or not summary.is_file():
        fail("generate_all.py", (generated.stdout + generated.stderr)[-800:])
    first_pass = summary.read_text(encoding="utf-8")
    check("the shipped template and generate_all.py produce a module summary")

    # Edit the source file and let the configured PostToolUse command run on
    # the same payload Claude Code would send. Nothing is simulated by hand:
    # the command comes from the settings.json init wrote.
    source.write_text(
        "def greet(name):\n    return f'hello {name}'\n\n\n"
        "def farewell(name):\n    return f'bye {name}'\n", encoding="utf-8")
    settings = json.loads((project / ".claude" / "settings.json")
                          .read_text(encoding="utf-8"))
    owned = [group for group in settings.get("hooks", {}).get("PostToolUse", [])
             if any("run_hook" in hook.get("command", "")
                    for hook in group.get("hooks", []))]
    if len(owned) != 1:
        fail("the hook entry", f"expected exactly one owned PostToolUse entry, found {len(owned)}")
    command = owned[0]["hooks"][0]["command"]
    payload = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Write",
                          "tool_input": {"file_path": str(source)},
                          "tool_response": {}})
    # The entry is a shell command; run it as the harness would, stdin included.
    hook = run([], cwd=project, env=env, input_text=payload, timeout=180,
               shell_string=command)
    if not summary.is_file():
        fail("the PostToolUse hook",
             f"no AI_SUMMARY.md after the edit; hook output:\n"
             f"{hook.stdout[-600:]}{hook.stderr[-600:]}")
    second_pass = summary.read_text(encoding="utf-8")
    if "farewell" not in second_pass:
        fail("the PostToolUse hook",
             "the summary was not regenerated: the new function is absent")
    if second_pass == first_pass:
        fail("the PostToolUse hook", "the summary did not change after the edit")
    check("the configured hook regenerates the module summary after an edit")

    update = cli(ainative, project, env, "update", "check")
    if update.returncode != 0:
        fail("ainative update check", update.stdout[-600:] + update.stderr[-400:])
    check("ainative update check answers without error")

    uninstall = cli(ainative, project, env, "uninstall", "--dry-run")
    if uninstall.returncode != 0:
        fail("ainative uninstall --dry-run", uninstall.stdout[-600:])
    if not (project / "src" / "main.py").is_file():
        fail("uninstall --dry-run", "the dry run touched the project")
    check("ainative uninstall --dry-run previews without touching anything")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, default=None,
                        help="test this wheel instead of building one "
                             "(e.g. a published release asset)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the workspace for inspection")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="colleague-e2e-"))
    print(f"workspace: {root}")
    try:
        dist = root / "dist"
        dist.mkdir()
        wheel = args.wheel.resolve() if args.wheel else build_wheel(dist)
        if not wheel.is_file():
            fail("the wheel", f"{wheel} does not exist")
        venv_python, ainative, bin_dir = make_venv(root, wheel)
        env = user_env(bin_dir)
        project = root / "project"
        project.mkdir()
        run_documented_flow(venv_python, ainative, project, env)
    except CheckFailed as error:
        print(f"\nCOLLEAGUE E2E: FAIL — {error}", file=sys.stderr)
        return 1
    finally:
        if args.keep:
            print(f"kept: {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\nCOLLEAGUE E2E: PASS ({len(CHECKPOINTS)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
