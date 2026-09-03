"""Two synthetic structural regressions for the V2 core.

This is NOT the blind historical validation the plan requires in section 44.
It asserts a synthetic REQ_WITHOUT_TASK gap and a direct-mutation detection,
neither of which is a historical incident. The real protocol, and the fact
that no run of it exists, are recorded in
docs/verified-work-plane-v2-historical-validation-protocol.md.
"""

from __future__ import annotations

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative_workplane.controller import ControllerError, WorkController
from ainative_workplane.traceability import analyze


def run() -> bool:
    requirement_gap = analyze(
        [{"uid": "req-history", "acceptance_criteria": []}], [], [], []
    )
    gap_ok = any(gap.code == "REQ_WITHOUT_TASK" for gap in requirement_gap.gaps)
    with tempfile.TemporaryDirectory() as directory:
        controller = WorkController(directory)
        committed = controller.create({"scratch": {"historical": True}})
        target = Path(directory) / committed["artifacts"]["scratch"]["path"]
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
