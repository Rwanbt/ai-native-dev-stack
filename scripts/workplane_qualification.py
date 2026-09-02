"""Record reproducible Work Plane qualification evidence from one named harness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests.test_workplane_cli tests.test_workplane_snapshot "
    "tests.test_workplane_convergence_history tests.test_workplane_runner_convergence "
    "tests.test_workplane_traceability tests.test_workplane_controller "
    "tests.test_workplane_contracts tests.test_workplane_integrations_metrics "
    "tests.test_workplane_pilot tests.test_workplane_harness_matrix "
    "tests.test_workplane_authorization tests.test_workplane_substance "
    "scripts.tests.test_vault_protocol scripts.tests.test_vault_sync_v4 hooks.tests.test_hooks_v4"
).split()


def _run(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    return {"command": command, "exit_code": result.returncode, "output_digest": sha256(output.encode("utf-8")).hexdigest()}


def run(harness_id: str) -> dict[str, object]:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    gates = (
        _run([sys.executable, "-m", "unittest", *TESTS, "-q"]),
        _run([sys.executable, "scripts/workplane_historical_validation.py"]),
        _run([sys.executable, "scripts/workplane_harness_matrix.py"]),
        _run([sys.executable, "scripts/workplane_pilot.py"]),
    )
    return {
        "schema_version": 1,
        "harness_id": harness_id,
        "commit": commit,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "passed": all(gate["exit_code"] == 0 for gate in gates),
        "authority": "qualification_evidence_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.harness_id)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
