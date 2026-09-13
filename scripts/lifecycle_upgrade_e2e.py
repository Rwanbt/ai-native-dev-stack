#!/usr/bin/env python3
"""The real upgrade transition: an older runtime refuses, the new one applies.

This is not a fixture pair declared as N and N+1. It builds two real wheels and
drives the console script in a fresh virtual environment:

    N   - the release under test: the current tree, built by `pip wheel`, the
          same artifact the release workflow publishes (or a real published
          wheel supplied with --wheel).
    N+1 - a probe target: the same pipeline, run over a relabelled copy of the
          tree whose VERSION, package version and AGENTS.md header say N+1.

Why N is the release under test and not the previous published release: the
CLI_UPDATE_REQUIRED refusal ships *in this release*. The published v2.2.1
predates it and would apply anything it is pointed at - that gap is permanent
history, not something a later release can retrofit. The property that must
hold from this release onward is: an installed runtime refuses any target whose
version differs from its own, and the target becomes applicable once the
matching runtime is installed. That property is what this script proves, with
two installed packages and no mocking.

Flow:
    1. build wheel N (or reuse a published one), install it in a fresh venv;
    2. `ainative init --profile standard` into a fresh project;
    3. publish N+1 through a local release index (bundle + releases.json);
    4. `ainative update` from runtime N -> CLI_UPDATE_REQUIRED, zero writes;
    5. install wheel N+1 in the same venv, verify `ainative --version`;
    6. `ainative update` -> applied; state and assets are N+1;
    7. rollback dry-run says so; real rollback restores N;
    8. flip one byte of the bundle -> UPDATE_INTEGRITY_FAILED, zero writes.

Usage:
    python scripts/lifecycle_upgrade_e2e.py
    python scripts/lifecycle_upgrade_e2e.py --wheel path/to/ainative_dev_stack-N-py3-none-any.whl
    python scripts/lifecycle_upgrade_e2e.py --keep     # inspect the workspace

Exits 0 only when every step passed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ainative.lifecycle.digest import digest_file  # noqa: E402

CHECKS: list[str] = []


class Failure(RuntimeError):
    """A step that must not fail did."""


def ok(message: str) -> None:
    CHECKS.append(message)
    print(f"[ok] {message}")


def run(argv, *, env=None, cwd=None, expect: int | None = 0, timeout=1800):
    completed = subprocess.run([str(item) for item in argv], cwd=cwd,
                               env={**os.environ, **(env or {})},
                               capture_output=True, text=True, stdin=subprocess.DEVNULL,
                               timeout=timeout)
    if expect is not None and completed.returncode != expect:
        raise Failure(
            f"command exited {completed.returncode}, expected {expect}: "
            + " ".join(map(str, argv))
            + f"\n--- stdout\n{completed.stdout[-3000:]}"
            + f"\n--- stderr\n{completed.stderr[-3000:]}")
    return completed


def snapshot(project: Path) -> dict:
    return {path.relative_to(project).as_posix(): digest_file(path) or ""
            for path in project.rglob("*") if path.is_file()}


def state_of(project: Path) -> dict:
    return json.loads((project / ".ai-native" / "lifecycle" / "state.json")
                      .read_text(encoding="utf-8"))


def bump_patch(version: str) -> str:
    major, minor, patch = version.split(".")[:3]
    return f"{major}.{minor}.{int(patch) + 1}"


def python_in(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def console_in(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "ainative.exe"
    return venv / "bin" / "ainative"

def relabel_tree(source_root: Path, destination: Path, version: str) -> Path:
    """A copy of the tree whose three version labels say `version`."""

    shutil.copytree(source_root, destination,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc",
                                                  ".pytest_cache", "build", "dist",
                                                  "*.egg-info", ".ai-native", ".gstack",
                                                  "node_modules", ".venv", "venv"))
    (destination / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    init = destination / "ainative" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    marker = '__version__ = "'
    start = text.index(marker) + len(marker)
    end = text.index('"', start)
    init.write_text(text[:start] + version + text[end:], encoding="utf-8")
    agents = destination / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    relabelled = re.sub(r"(stack-version:\s*)[0-9][0-9A-Za-z.\-]*",
                        rf"\g<1>{version}", text, count=1)
    agents.write_text(relabelled, encoding="utf-8")
    return destination


def build_wheel(tree: Path, output: Path) -> Path:
    run([sys.executable, "-m", "pip", "wheel", "--disable-pip-version-check",
         "--no-deps", "--wheel-dir", output, tree])
    wheels = sorted(output.glob("*.whl"))
    if len(wheels) != 1:
        raise Failure(f"expected one wheel from {tree}, found {wheels}")
    return wheels[0]


def build_bundle(tree: Path, output: Path) -> Path:
    run([sys.executable, str(tree / "scripts" / "build_lifecycle_bundle.py"),
         "--outdir", output])
    bundles = sorted(output.glob("ainative-dev-stack-*.zip"))
    if len(bundles) != 1:
        raise Failure(f"expected one bundle from {tree}, found {bundles}")
    return bundles[0]


def publish(releases: Path, version: str, bundle: Path) -> None:
    payload = {"channels": {"stable": {
        "version": version, "archive": bundle.name,
        "sha256": sha256(bundle.read_bytes()).hexdigest(),
        "notes": f"probe release {version}"}}}
    (releases / "releases.json").write_text(json.dumps(payload, indent=2) + "\n",
                                            encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wheel", default=None,
                        help="a prebuilt wheel to use as runtime N "
                             "(default: build one from this tree)")
    parser.add_argument("--from-version", default=None,
                        help="runtime N version (default: this checkout's VERSION)")
    parser.add_argument("--to-version", default=None,
                        help="probe target N+1 version (default: N + 1 patch)")
    parser.add_argument("--keep", action="store_true",
                        help="keep the workspace and print its path")
    args = parser.parse_args()

    from _payload_staging import read_version

    from_version = args.from_version or read_version(REPO)
    if args.wheel and not args.from_version:
        raise Failure("--wheel requires --from-version naming the wheel's version")
    to_version = args.to_version or bump_patch(from_version)
    if to_version == from_version:
        raise Failure("the probe target must differ from the runtime under test")

    workspace = Path(tempfile.mkdtemp(prefix="ainative-upgrade-e2e-"))
    failed = False
    try:
        venv = workspace / "venv"
        run([sys.executable, "-m", "venv", venv])
        venv_python = python_in(venv)
        console = console_in(venv)

        if args.wheel:
            wheel_n = Path(args.wheel).resolve()
            if not wheel_n.is_file():
                raise Failure(f"wheel not found: {wheel_n}")
        else:
            wheel_n = build_wheel(REPO, workspace / "dist-n")
        run([venv_python, "-m", "pip", "install", "--disable-pip-version-check",
             "-q", "--no-deps", wheel_n])
        ok(f"runtime N {from_version} installed from {wheel_n.name}")

        project = workspace / "project"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
        run([console, "init", "--profile", "standard", "--project", project],
            env={"AINATIVE_STACK_SOURCE": ""})
        version_report = run([console, "--version"])
        if f"lifecycle: {from_version}" not in version_report.stdout:
            raise Failure(f"installed runtime is not {from_version}:\n{version_report.stdout}")
        installed_state = state_of(project)
        if installed_state["stack_version"] != from_version:
            raise Failure(f"fresh project is at {installed_state['stack_version']}, "
                          f"expected {from_version}")
        ok(f"project initialized at {from_version} by the {from_version} runtime")

        probe_tree = relabel_tree(REPO, workspace / "probe", to_version)
        wheel_n1 = build_wheel(probe_tree, workspace / "dist-n1")
        releases = workspace / "releases"
        releases.mkdir()
        bundle_n1 = build_bundle(probe_tree, releases)
        if bundle_n1.name != f"ainative-dev-stack-{to_version}.zip":
            raise Failure(f"probe bundle is {bundle_n1.name}, expected the canonical name")
        publish(releases, to_version, bundle_n1)
        provider_env = {"AINATIVE_UPDATE_PROVIDER": "local",
                        "AINATIVE_UPDATE_LOCAL_DIR": str(releases)}
        ok(f"probe release {to_version} published through a local index")

        before = snapshot(project)
        refused = run([console, "update", "--project", project], env=provider_env, expect=1)
        if "CLI_UPDATE_REQUIRED" not in refused.stderr:
            raise Failure(f"the old runtime did not refuse:\n{refused.stdout}\n{refused.stderr}")
        if snapshot(project) != before:
            raise Failure("the refused update wrote to the project")
        if state_of(project)["stack_version"] != from_version:
            raise Failure("the refused update moved the project state")
        ok(f"runtime {from_version} refused target {to_version}: "
           f"CLI_UPDATE_REQUIRED, zero writes")

        run([venv_python, "-m", "pip", "install", "--disable-pip-version-check",
             "-q", "--upgrade", "--no-deps", wheel_n1])
        version_report = run([console, "--version"])
        if f"lifecycle: {to_version}" not in version_report.stdout:
            raise Failure(f"runtime upgrade failed:\n{version_report.stdout}")
        ok(f"runtime upgraded to {to_version} in the same environment")

        applied = run([console, "update", "--project", project], env=provider_env)
        state = state_of(project)
        if state["stack_version"] != to_version or state["source_version"] != to_version:
            raise Failure(f"update did not land: {state['stack_version']}/"
                          f"{state['source_version']}, expected {to_version}")
        expected_agents = (probe_tree / "AGENTS.md").read_bytes()
        if (project / "AGENTS.md").read_bytes() != expected_agents:
            raise Failure("project assets are not the probe release's assets")
        ok(f"project updated to {to_version}: state, source_version and assets agree")

        before_rollback = snapshot(project)
        dry = run([console, "update", "rollback", "--dry-run", "--project", project])
        if "would roll back" not in dry.stdout or "rolled back to" in dry.stdout:
            raise Failure(f"dry-run wording is wrong:\n{dry.stdout}")
        if snapshot(project) != before_rollback:
            raise Failure("the dry-run rollback wrote to the project")
        run([console, "update", "rollback", "--project", project])
        if state_of(project)["stack_version"] != from_version:
            raise Failure("the rollback did not restore the previous version")
        ok(f"rollback dry-run writes nothing; a real rollback restores {from_version}")

        mutated = bytearray(bundle_n1.read_bytes())
        mutated[-1] ^= 0xFF
        bundle_n1.write_bytes(bytes(mutated))
        before_digest = snapshot(project)
        digest_failure = run([console, "update", "--project", project],
                             env=provider_env, expect=1)
        if "UPDATE_INTEGRITY_FAILED" not in digest_failure.stderr:
            raise Failure(f"the tampered bundle was not refused:\n{digest_failure.stderr}")
        if snapshot(project) != before_digest:
            raise Failure("the tampered bundle wrote to the project")
        ok("tampered bundle: UPDATE_INTEGRITY_FAILED, zero writes")

        print(f"\nUPGRADE E2E: PASS ({len(CHECKS)} checks, "
              f"{from_version} -> {to_version} -> refusal -> upgrade)")
        return 0
    except Failure as error:
        failed = True
        print(f"\nUPGRADE E2E: FAIL\n{error}", file=sys.stderr)
        return 1
    finally:
        if args.keep or failed:
            print(f"workspace kept for inspection: {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())