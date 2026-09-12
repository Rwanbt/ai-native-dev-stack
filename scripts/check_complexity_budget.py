"""Measure the complexity budget conventions.json declares, on the plane.

AGENTS.md declares the rule and conventions.json is its machine-readable twin;
this checker reads the canonical value instead of re-declaring it (#39): a
threshold copied into a third file is enforced at two values the day one of
them changes.

The stack gated its own LOC budget in CI but never measured the complexity
budget it publishes, so `traceability.analyze` shipped at roughly 32 branches
in a module every convergence verdict passes through.

Behaviour preservation is the traceability suite's job; this check is the
budget, plus the assertion that the refactored module still answers.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Both shipped packages. The lifecycle layer decides what to delete from a
# user's project; publishing a budget and measuring only half the code that
# enforces it is the same omission this script was written for.
PACKAGES = (REPO / "ainative_workplane", REPO / "ainative", REPO / "ainative" / "lifecycle")
BRANCHING = (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.comprehension)
CONVENTIONS = "conventions.json"


class ConventionBudgetMissing(RuntimeError):
    """conventions.json does not declare a usable blocking budget."""


def read_blocking_budget(root: Path) -> int:
    """The blocking threshold conventions.json declares, or a refusal.

    Never a default and never a fallback: a checker running on an invented
    value is worse than a checker that refuses to run.
    """

    path = root / CONVENTIONS
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload["cyclomatic_complexity"]["blocking"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ConventionBudgetMissing(
            f"cannot read cyclomatic_complexity.blocking from {path}: {error}") from error
    # bool is an int in Python; a boolean threshold is not a threshold.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConventionBudgetMissing(
            f"{path} declares an invalid cyclomatic_complexity.blocking: {value!r}")
    return value

def complexity(node: ast.AST) -> int:
    return sum(isinstance(child, BRANCHING) for child in ast.walk(node)) + 1


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO).as_posix())
    except ValueError:
        return str(path)


def measure(package: Path, blocking: int) -> tuple[list[dict], int]:
    """Findings over the budget in one package, and how many functions ran."""

    findings, counted = [], 0
    for path in sorted(package.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            counted += 1
            measured = complexity(node)
            if measured > blocking:
                findings.append({
                    "file": _display(path),
                    "function": node.name, "complexity": measured,
                    "detail": f"exceeds the blocking budget of {blocking} "
                              "declared in conventions.json"})
    return findings, counted


def main() -> int:
    try:
        blocking = read_blocking_budget(REPO)
    except ConventionBudgetMissing as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    findings, checked = [], 0
    for package in PACKAGES:
        package_findings, counted = measure(package, blocking)
        findings.extend(package_findings)
        checked += counted

    completed = subprocess.run([sys.executable, "-m", "unittest", "tests.test_workplane_traceability", "-q"],
                               cwd=REPO, capture_output=True, text=True, timeout=600, check=False)
    checked += 1
    if completed.returncode != 0:
        findings.append({"file": "tests/test_workplane_traceability.py", "function": "<suite>", "complexity": 0,
                         "detail": (completed.stdout + completed.stderr)[-300:]})

    print(json.dumps({"observations": checked, "blocking_budget": blocking, "findings": findings},
                     sort_keys=True))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())