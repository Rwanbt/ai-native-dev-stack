#!/usr/bin/env python3
"""Published-artifact gate: the OpenCode plugin, rendered by the real wheel.

The source-level runtime gate (scripts/opencode_plugin_runtime_e2e.py) proves the
template is runtime-compatible. It cannot prove that a user who installs the
published wheel gets a working plugin at all: before this gate, the staged
payload carried no `adapters/` tree, so `ainative machine init` skipped the
plugin with a visible SKIP and the documented OpenCode integration existed for
checkout users only.

So this gate never reads the checkout's template. It builds the wheel (or takes
`--wheel` — the released bytes, for a post-release run), installs it into a
fresh venv, runs `ainative machine init` against a throwaway home, then hands
the *installed* plugin to the runtime driver. The plugin must come out of the
venv's own payload; a rendered copy pointing back at this checkout fails the
gate.

Usage:
    python scripts/opencode_plugin_published_e2e.py
    python scripts/opencode_plugin_published_e2e.py --wheel dist/ainative_dev_stack-2.5.0-py3-none-any.whl
    python scripts/opencode_plugin_published_e2e.py --keep
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

REPO = Path(__file__).resolve().parents[1]
RUNTIME_GATE = REPO / "scripts" / "opencode_plugin_runtime_e2e.py"
PLUGIN_RELATIVE = Path(".config") / "opencode" / "plugins" / "ai-native-dev-stack.ts"
STEP_TIMEOUT_SECONDS = 900


class Failure(SystemExit):
    pass


def run(command: list[str], *, cwd: Path | None = None, env: dict | None = None,
        expect: int = 0) -> subprocess.CompletedProcess:
    completed = subprocess.run([str(item) for item in command],
                               cwd=str(cwd) if cwd else None, env=env,
                               capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=STEP_TIMEOUT_SECONDS)
    if completed.returncode != expect:
        print(completed.stdout[-2000:])
        print(completed.stderr[-2000:], file=sys.stderr)
        raise Failure(f"expected exit {expect}, got {completed.returncode}: {command}")
    return completed


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(f"FAILED: {message}")
    print(f"  [PASS] {message}")


def clean_environment() -> dict:
    return {key: value for key, value in os.environ.items()
            if key not in ("PYTHONPATH", "AINATIVE_STACK_SOURCE", "OBSIDIAN_VAULT",
                           "OBSIDIAN_PROJECT_SLUG")}


def build_wheel(root: Path) -> Path:
    print("[1] build the wheel the user would install")
    distribution = root / "dist"
    run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q",
         "build"])
    run([sys.executable, "-m", "build", "--wheel", "--outdir", distribution], cwd=REPO)
    wheel = next(distribution.glob("*.whl"))
    print(f"      wheel: {wheel.name}")
    return wheel


def install(wheel: Path, root: Path) -> tuple[Path, Path]:
    print("[2] install it into a fresh venv")
    venv = root / "venv"
    run([sys.executable, "-m", "venv", venv])
    scripts = venv / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    ainative = scripts / ("ainative.exe" if os.name == "nt" else "ainative")
    run([python, "-m", "pip", "install", "--disable-pip-version-check", "-q", wheel])
    require(ainative.is_file(), "the wheel installs the ainative console script")
    return ainative, python


def machine_init(ainative: Path, home: Path, env: dict) -> Path:
    print("[3] ainative machine init renders the plugin from the installed payload")
    completed = run([ainative, "machine", "init", "--home", home, "--json"], env=env)
    report = json.loads(completed.stdout)
    require(report.get("changes", 0) > 0, "the machine init recorded changes")
    require(report.get("errors", 1) == 0, "the machine init reported no error")
    # The manifest path in the report may use the platform's short or long form
    # (Windows CI runs under RUNNER~1); compare resolved locations, not strings.
    manifest = report.get("manifest")
    require(isinstance(manifest, str) and Path(manifest).is_file()
            and Path(manifest).resolve().parent == (home / ".ai-native").resolve(),
            "the machine manifest was written under the throwaway home")

    plugin = home / PLUGIN_RELATIVE
    require(plugin.is_file(), f"the installed distribution renders {PLUGIN_RELATIVE}")
    return plugin


def assert_plugin_comes_from_the_wheel(plugin: Path, venv: Path) -> None:
    print("[4] the rendered plugin resolves to the installed payload, not this checkout")
    text = plugin.read_text(encoding="utf-8")
    require("readFile" in text and "node:fs/promises" in text
            and "node:child_process" in text,
            "the installed plugin carries the runtime-compatible implementation")
    require("Bun." not in text and "await $(" not in text,
            "the installed plugin carries no Bun runtime dependency")
    root_line = next((line for line in text.splitlines()
                      if line.startswith("const STACK_ROOT = ")), "")
    require(root_line != "", "the installed plugin declares its stack root")
    stack_root = json.loads(root_line.split("=", 1)[1].strip())
    require(Path(stack_root).is_relative_to(venv.resolve()),
            f"the plugin's stack root is inside the venv ({stack_root})")
    require(not Path(stack_root).is_relative_to(REPO.resolve()),
            "the plugin's stack root is not this checkout")
    require((Path(stack_root) / "adapters" / "opencode" / "ai-native-dev-stack.ts").is_file(),
            "the installed payload carries the plugin template it was rendered from")


def machine_doctor(ainative: Path, home: Path, env: dict) -> None:
    print("[5] ainative machine doctor accepts the recorded integration")
    completed = run([ainative, "machine", "doctor", "--home", home, "--json"], env=env)
    report = json.loads(completed.stdout)
    require(report.get("healthy") is True, "the machine doctor verdict is healthy")


def runtime_gate(plugin: Path, python: Path, env: dict) -> None:
    print("[6] the installed plugin passes the runtime gate (edit/write, AI_SUMMARY)")
    completed = run([sys.executable, RUNTIME_GATE, "--plugin", plugin,
                     "--python-exe", python], env=env)
    require("8/8 checks passed" in completed.stdout,
            "the installed plugin passes all 8 runtime checks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wheel", type=Path, default=None,
                        help="install this wheel instead of building one "
                             "(the released bytes, for a post-release run)")
    parser.add_argument("--keep", action="store_true", help="keep the workspace")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="opencode-published-"))
    home = root / "home"
    home.mkdir()
    # Resolve once: Windows temp paths can be 8.3 short names, and comparing a
    # short form with a resolved one made a passing install look wrong on CI.
    home = home.resolve()
    env = {**clean_environment(), "HOME": str(home), "USERPROFILE": str(home),
           "AINATIVE_NO_UPDATE_CHECK": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        wheel = args.wheel if args.wheel is not None else build_wheel(root)
        require(wheel.is_file(), f"the wheel to install exists: {wheel}")
        ainative, python = install(wheel, root)
        plugin = machine_init(ainative, home, env)
        assert_plugin_comes_from_the_wheel(plugin, root / "venv")
        machine_doctor(ainative, home, env)
        runtime_gate(plugin, python, env)
    finally:
        if args.keep:
            print(f"workspace kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)

    print("\nPUBLISHED OPENCODE PLUGIN: all gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
