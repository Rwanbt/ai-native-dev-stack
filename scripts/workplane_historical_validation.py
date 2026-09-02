"""Blind historical validation scenarios for the V2 structural core."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ainative_workplane.controller import ControllerError, WorkController
from ainative_workplane.traceability import analyze


def run() -> bool:
    requirement_gap = analyze(
        [{"uid": "req-history", "acceptance_criteria": []}], [], [], []
    )
    gap_ok = any(gap.code == "REQ_WITHOUT_TASK" for gap in requirement_gap.gaps)
    with tempfile.TemporaryDirectory() as directory:
        controller = WorkController(directory)
        committed = controller.create({"requirements": {"historical": True}})
        target = Path(directory) / committed["artifacts"]["requirements"]["path"]
        target.write_text('{"historical":false}', encoding="utf-8")
        try:
            controller.read()
        except ControllerError as error:
            mutation_ok = str(error) == "UNEXPECTED_MUTATION"
        else:
            mutation_ok = False
    print(f"historical requirement gap: {'PASS' if gap_ok else 'FAIL'}")
    print(f"historical direct mutation: {'PASS' if mutation_ok else 'FAIL'}")
    return gap_ok and mutation_ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
