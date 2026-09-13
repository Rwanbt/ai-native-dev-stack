#!/usr/bin/env python3
"""OpenCode plugin runtime gate: render the plugin, execute it, drive edit/write.

#153 was a runtime bug, not a unit-test bug: the plugin crashed at load with
`Bun.file is not defined`, and after every successful edit with
`$ is not a function`, so `update_on_edit.py` never ran. Tests that read the
template cannot catch either — only a runtime that loads the *rendered* file,
builds the plugin, and calls its hooks can.

This driver runs when the distribution is a checkout; the published path is
`scripts/opencode_plugin_published_e2e.py`, which points `--plugin` at the file
`ainative machine init` rendered from the installed wheel. Eight checks:

    1. the rendered plugin loads in a real runtime (global `Bun` is undefined)
    2. `edit`: before allows, after regenerates AI_SUMMARY.md
    3. `write`: before allows, after regenerates AI_SUMMARY.md
    4. an edit above the blocking LOC limit is refused, with the gate's message
    5. the blocking limit comes from conventions.json, not a hardcoded number
    6. an unreadable (typically new) path is not gated
    7. without a Python interpreter the after-hook skips, breaking no edit
    8. the runtime contract holds: node: imports, no Bun/`$` runtime dependency

Usage:
    python scripts/opencode_plugin_runtime_e2e.py
    python scripts/opencode_plugin_runtime_e2e.py --node /path/to/node
    python scripts/opencode_plugin_runtime_e2e.py --plugin <installed copy> \\
        --python-exe <venv python>            # the published-artifact path
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS = Path(__file__).resolve().parent / "harness" / "opencode-plugin-runtime.mjs"
TEMPLATE_RELATIVE = Path("adapters/opencode/ai-native-dev-stack.ts")
UPDATE_SCRIPT_RELATIVE = Path("tools/ai_docs/update_on_edit.py")
_STACK_ROOT_LITERAL = re.compile(r"^const STACK_ROOT = (.+)$", re.M)
FORBIDDEN_RUNTIME = ("Bun.", "Bun(", "await $(", "require(\"bun\")", "require('bun')")
REQUIRED_IMPORTS = ("node:fs/promises", "node:child_process")
FALLBACK_BLOCKING_LOC = 1500
STEP_TIMEOUT_SECONDS = 180
CHECKS = 8


class Failure(SystemExit):
    pass


def check(number: int, description: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {number}/{CHECKS} {description}")
    if not condition:
        raise Failure(f"FAILED {number}/{CHECKS}: {description}"
                      + (f"\n        {detail}" if detail else ""))


def run(command: list[str], *, env: dict | None = None,
        input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(item) for item in command], env=env,
                          input=input_text, capture_output=True, text=True,
                          timeout=STEP_TIMEOUT_SECONDS)


def node_command(node: str) -> list[str]:
    """Node 22.6+ needs --experimental-strip-types for .ts; 23.6+ defaults it."""

    probe = run([node, "--experimental-strip-types", "-e", "0"])
    if probe.returncode == 0:
        return [node, "--experimental-strip-types"]
    return [node]


def render_plugin(template: Path, stack_root: Path, destination: Path) -> str:
    text = template.read_text(encoding="utf-8")
    rendered = text.replace("{{STACK_ROOT_JSON}}", json.dumps(str(stack_root)))
    if "{{STACK_ROOT_JSON}}" in rendered:
        raise Failure(f"{template} still carries an unrendered placeholder")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    return rendered


def embedded_stack_root(plugin: Path) -> str:
    match = _STACK_ROOT_LITERAL.search(plugin.read_text(encoding="utf-8"))
    if match is None:
        raise Failure(f"{plugin} carries no STACK_ROOT literal; not a rendered plugin")
    return json.loads(match.group(1))


def blocking_loc(stack_root: Path) -> int:
    try:
        conventions = json.loads((stack_root / "conventions.json").read_text(encoding="utf-8"))
        value = conventions.get("file_size", {}).get("blocking")
        return int(value) if isinstance(value, int) and value > 0 else FALLBACK_BLOCKING_LOC
    except (OSError, ValueError):
        return FALLBACK_BLOCKING_LOC


def hook_step(step_id: str, hook: str, tool: str, call_id: str, file_path: Path) -> dict:
    return {"id": step_id, "hook": hook,
            "input": {"tool": tool, "callID": call_id},
            "output": {"args": {"filePath": str(file_path)}}}


def execute_plan(prefix: list[str], plugin: Path, workspace: Path,
                 steps: list[dict], env: dict) -> dict:
    plan_file = workspace / "plan.json"
    plan_file.write_text(json.dumps({"plugin": str(plugin), "workspace": str(workspace),
                                     "steps": steps}), encoding="utf-8")
    completed = run([*prefix, str(HARNESS), str(plan_file)], env=env)
    try:
        return json.loads(completed.stdout)
    except ValueError:
        raise Failure("the runtime harness produced no JSON report\n"
                      f"stdout:\n{completed.stdout[-1500:]}\n"
                      f"stderr:\n{completed.stderr[-1500:]}") from None


def write_module(workspace: Path, name: str = "main") -> Path:
    module = workspace / "src"
    module.mkdir(parents=True, exist_ok=True)
    (module / "AI_CONTEXT.md").write_text(
        "# src — harness module\n\nPurpose: exercise the plugin hooks.\n", encoding="utf-8")
    source = module / f"{name}.py"
    source.write_text("def greet(name):\n    return f\"hello {name}\"\n", encoding="utf-8")
    return source


def step_ok(report: dict, step_id: str) -> dict:
    for entry in report.get("steps", []):
        if entry["id"] == step_id:
            return entry
    raise Failure(f"the harness reported no step {step_id!r}: {report}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--node", default=shutil.which("node") or "node",
                        help="the node executable (default: on PATH)")
    parser.add_argument("--stack-root", type=Path, default=REPO,
                        help="distribution root holding the template (default: this checkout)")
    parser.add_argument("--plugin", type=Path, default=None,
                        help="an already-rendered plugin (the published artifact); "
                             "the stack root is read from its STACK_ROOT literal")
    parser.add_argument("--python-exe", type=Path, default=None,
                        help="a Python whose directory is prepended to PATH for the hooks")
    parser.add_argument("--keep", action="store_true", help="keep the workspace")
    args = parser.parse_args()

    if not HARNESS.is_file():
        raise Failure(f"the runtime harness is missing: {HARNESS}")
    prefix = node_command(args.node)
    root = Path(tempfile.mkdtemp(prefix="opencode-runtime-"))
    try:
        return qualify(prefix, root, args)
    finally:
        if args.keep:
            print(f"workspace kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


def qualify(prefix: list[str], root: Path, args) -> int:
    print("OpenCode plugin runtime gate")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if args.python_exe is not None:
        env["PATH"] = str(Path(args.python_exe).parent) + os.pathsep + env.get("PATH", "")

    if args.plugin is not None:
        plugin = args.plugin.resolve()
        if not plugin.is_file():
            raise Failure(f"the installed plugin does not exist: {plugin}")
        stack_root = Path(embedded_stack_root(plugin))
        template = None
    else:
        stack_root = args.stack_root.resolve()
        template = stack_root / TEMPLATE_RELATIVE
        if not template.is_file():
            raise Failure(f"the distribution carries no plugin template: {template}")
        plugin = root / "rendered" / "ai-native-dev-stack.ts"
        plugin.parent.mkdir(parents=True, exist_ok=True)
        render_plugin(template, stack_root, plugin)

    print(f"  plugin: {plugin}")
    print(f"  stack root: {stack_root}")

    # 1 — the rendered file loads in a real runtime, which has no global Bun.
    workspace = root / "workspace"
    workspace.mkdir()
    report = execute_plan(prefix, plugin, workspace, [], env)
    check(1, "the rendered plugin loads in a real runtime (global Bun is undefined)",
          report.get("loaded") is True
          and report.get("globalBun") == "undefined"
          and report.get("hooks") == ["tool.execute.after", "tool.execute.before"],
          json.dumps(report)[:1200])

    # 2 — edit: before allows, after runs update_on_edit.py and regenerates.
    source = write_module(workspace)
    summary = source.parent / "AI_SUMMARY.md"
    steps = [hook_step("edit-before", "tool.execute.before", "edit", "c1", source),
             hook_step("edit-after", "tool.execute.after", "edit", "c1", source)]
    report = execute_plan(prefix, plugin, workspace, steps, env)
    first = summary.read_text(encoding="utf-8") if summary.is_file() else ""
    first_ok = (step_ok(report, "edit-before")["ok"] and step_ok(report, "edit-after")["ok"]
                and "greet" in first)

    source.write_text("def greet(name):\n    return f\"hello {name}\"\n\n\n"
                      "def farewell(name):\n    return f\"bye {name}\"\n", encoding="utf-8")
    steps = [hook_step("edit2-before", "tool.execute.before", "edit", "c2", source),
             hook_step("edit2-after", "tool.execute.after", "edit", "c2", source)]
    report = execute_plan(prefix, plugin, workspace, steps, env)
    second = summary.read_text(encoding="utf-8") if summary.is_file() else ""
    check(2, "edit: before allows, after regenerates AI_SUMMARY.md",
          first_ok and step_ok(report, "edit2-before")["ok"]
          and step_ok(report, "edit2-after")["ok"]
          and "farewell" in second and second != first,
          json.dumps(report)[:1200])

    # 3 — write follows the same lifecycle.
    helper = source.parent / "helper.py"
    helper.write_text("def assist(value):\n    return value + 1\n", encoding="utf-8")
    steps = [hook_step("write-before", "tool.execute.before", "write", "w1", helper),
             hook_step("write-after", "tool.execute.after", "write", "w1", helper)]
    report = execute_plan(prefix, plugin, workspace, steps, env)
    written = summary.read_text(encoding="utf-8") if summary.is_file() else ""
    check(3, "write: before allows, after regenerates AI_SUMMARY.md",
          step_ok(report, "write-before")["ok"] and step_ok(report, "write-after")["ok"]
          and "assist" in written,
          json.dumps(report)[:1200])

    # 4 — the blocking limit refuses the edit and names the gate.
    limit = blocking_loc(stack_root)
    big = source.parent / "big.py"
    big.write_text("value = 1\n" * (limit + 1), encoding="utf-8")
    steps = [hook_step("gate", "tool.execute.before", "edit", "b1", big)]
    report = execute_plan(prefix, plugin, workspace, steps, env)
    refusal = step_ok(report, "gate")
    check(4, f"an edit above the blocking LOC limit ({limit}) is refused",
          refusal["ok"] is False and "LOC gate" in refusal.get("error", "")
          and str(limit) in refusal.get("error", ""),
          json.dumps(report)[:1200])

    # 5 — the limit is read from conventions.json at runtime, not hardcoded.
    synthetic_root = root / "synthetic-stack"
    synthetic_root.mkdir()
    (synthetic_root / "conventions.json").write_text(
        json.dumps({"file_size": {"blocking": 10}}), encoding="utf-8")
    synthetic_plugin = root / "rendered" / "synthetic.ts"
    render_plugin(template if template else stack_root / TEMPLATE_RELATIVE,
                  synthetic_root, synthetic_plugin)
    synthetic_workspace = root / "synthetic-workspace"
    synthetic_workspace.mkdir()
    small = synthetic_workspace / "small.py"
    small.write_text("value = 1\n" * 5, encoding="utf-8")
    over = synthetic_workspace / "over.py"
    over.write_text("value = 1\n" * 11, encoding="utf-8")
    steps = [hook_step("config-small", "tool.execute.before", "edit", "s1", small),
             hook_step("config-over", "tool.execute.before", "edit", "s2", over)]
    report = execute_plan(prefix, synthetic_plugin, synthetic_workspace, steps, env)
    over_entry = step_ok(report, "config-over")
    check(5, "the blocking limit comes from conventions.json (10, not the fallback)",
          step_ok(report, "config-small")["ok"] is True
          and over_entry["ok"] is False and "10" in over_entry.get("error", ""),
          json.dumps(report)[:1200])

    # 6 — a path that does not exist yet (a new file) is not gated.
    steps = [hook_step("new-file", "tool.execute.before", "write", "n1",
                       workspace / "src" / "not-written-yet.py")]
    report = execute_plan(prefix, plugin, workspace, steps, env)
    check(6, "an unreadable (typically new) path is not gated",
          step_ok(report, "new-file")["ok"] is True, json.dumps(report)[:1200])

    # 7 — no Python anywhere: the after-hook skips and the edit still succeeds.
    barren = root / "no-python"
    barren.mkdir()
    no_python_env = {**env, "PATH": str(barren)}
    before_bytes = summary.read_bytes()
    steps = [hook_step("nopy-before", "tool.execute.before", "edit", "p1", source),
             hook_step("nopy-after", "tool.execute.after", "edit", "p1", source)]
    report = execute_plan(prefix, plugin, workspace, steps, no_python_env)
    check(7, "without a Python interpreter the after-hook skips, breaking no edit",
          step_ok(report, "nopy-before")["ok"] and step_ok(report, "nopy-after")["ok"]
          and summary.read_bytes() == before_bytes,
          json.dumps(report)[:1200])

    # 8 — the runtime contract, on the exact bytes the runtime loads.
    text = plugin.read_text(encoding="utf-8")
    forbidden = [pattern for pattern in FORBIDDEN_RUNTIME if pattern in text]
    missing = [name for name in REQUIRED_IMPORTS if name not in text]
    check(8, "the runtime contract holds: node: imports, no Bun/$ runtime dependency",
          not forbidden and not missing,
          f"forbidden={forbidden} missing={missing}")

    print(f"\nOPENCODE PLUGIN RUNTIME: {CHECKS}/{CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Failure as refusal:
        print(str(refusal), file=sys.stderr)
        raise SystemExit(1) from None
