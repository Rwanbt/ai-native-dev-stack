"""AGENTS.md declares >25 cyclomatic complexity blocking. Enforce it on the plane.

The stack gates its own LOC budget in CI but never measured the complexity
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
BLOCKING = 25
BRANCHING = (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.comprehension)


def complexity(node: ast.AST) -> int:
    return sum(isinstance(child, BRANCHING) for child in ast.walk(node)) + 1


def main() -> int:
    findings, checked = [], 0
    for package in PACKAGES:
        for path in sorted(package.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                checked += 1
                measured = complexity(node)
                if measured > BLOCKING:
                    findings.append({
                        "file": str(path.relative_to(REPO).as_posix()),
                        "function": node.name, "complexity": measured,
                        "detail": f"exceeds the blocking budget of {BLOCKING} declared in AGENTS.md"})

    completed = subprocess.run([sys.executable, "-m", "unittest", "tests.test_workplane_traceability", "-q"],
                               cwd=REPO, capture_output=True, text=True, timeout=600, check=False)
    checked += 1
    if completed.returncode != 0:
        findings.append({"file": "tests/test_workplane_traceability.py", "function": "<suite>", "complexity": 0,
                         "detail": (completed.stdout + completed.stderr)[-300:]})

    print(json.dumps({"observations": checked, "blocking_budget": BLOCKING, "findings": findings}, sort_keys=True))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
