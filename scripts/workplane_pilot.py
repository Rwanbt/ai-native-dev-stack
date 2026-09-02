"""Local five-work-item pilot for the V2 core."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative_workplane.controller import WorkController
from ainative_workplane.convergence import converge
from ainative_workplane.metrics import PilotMetrics
from ainative_workplane.runner import VerificationRunner
from ainative_workplane.traceability import analyze


def run() -> dict[str, object]:
    registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('pilot pass')"], "timeout_seconds": 3, "max_output_bytes": 1024}}}
    kinds = ["feature", "feature", "bugfix", "refactor", "hotfix"]
    started = time.monotonic()
    convergence_started = time.monotonic()
    completed = 0
    with tempfile.TemporaryDirectory(prefix="workplane-pilot-") as directory:
        root = Path(directory)
        for index, kind in enumerate(kinds, 1):
            work = root / f"work-{index}"
            controller = WorkController(work)
            controller.create({"task": {"kind": kind, "index": index}})
            controller.mutate(1, {"task": {"kind": kind, "index": index, "verified": True}})
            result = VerificationRunner(registry).run("check", cwd=work)
            if result.status != "PASS":
                raise RuntimeError(f"pilot verification failed for {kind}: {result.status}")
            completed += 1
        verdict = converge(analyze([], [], [], []), [{"uid": "pilot-run", "status": "PASS"}])
        if verdict.verdict != "CONVERGED":
            raise RuntimeError(f"pilot convergence failed: {verdict.verdict}")
        elapsed = int((time.monotonic() - started) * 1000)
        convergence_elapsed = int((time.monotonic() - convergence_started) * 1000)
    metrics = PilotMetrics(setup_time_ms=elapsed, verification_runtime_ms=elapsed, convergence_runtime_ms=convergence_elapsed)
    return {"work_items": len(kinds), "completed": completed, "kinds": kinds, "metrics": metrics.__dict__, "external_harness": False}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
