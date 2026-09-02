"""Local five-work-item pilot for the V2 core."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative_workplane.controller import WorkController
from ainative_workplane.contracts import canonical_digest, generate_uid
from ainative_workplane.convergence import converge
from ainative_workplane.freshness import evaluate_freshness
from ainative_workplane.metrics import PilotMetrics
from ainative_workplane.runner import VerificationRunner
from ainative_workplane.traceability import analyze
from ainative_workplane.trust import evaluate_trust


def run() -> dict[str, object]:
    registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('pilot pass')"], "timeout_seconds": 3, "max_output_bytes": 1024}}}
    kinds = ["feature", "feature", "bugfix", "refactor", "hotfix"]
    started = time.monotonic()
    convergence_started = time.monotonic()
    completed = 0
    digest = "a" * 64
    registry_digest = canonical_digest(registry)
    policy = {"schema_name": "project_policy", "schema_version": 1, "approval_predicate": {"predicate_id": "local"}, "success_condition_mutation_provenance": "LOCAL_UNTRUSTED", "verification_evidence_provenance": "LOCAL_UNTRUSTED", "waiver_approval_rule": {"predicate_id": "local", "policy_digest": digest}, "human_approval_rule": {"predicate_id": "local", "policy_digest": digest}, "promotion_policy": "explicit"}
    approval_root = {"schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"), "root_digest": digest, "root_provenance": "LOCAL_UNTRUSTED", "bootstrap": {"initialized_at": "2026-09-02T00:00:00Z", "initialized_by": "pilot"}}

    def binding() -> dict[str, object]:
        reference = lambda prefix: {"uid": generate_uid(prefix), "digest": digest}
        return {"work": reference("work"), "contract_revision": 1, "contract_digest": digest, "verification_specification": reference("verify"), "command_registry_digest": registry_digest, "policy_digest": digest, "approval_root": {"uid": approval_root["uid"], "digest": approval_root["root_digest"]}, "repository_snapshot": reference("snapshot"), "producer": "local-pilot", "producer_version": "1", "evidence_provenance": "LOCAL_UNTRUSTED"}
    with tempfile.TemporaryDirectory(prefix="workplane-pilot-") as directory:
        root = Path(directory)
        for index, kind in enumerate(kinds, 1):
            work = root / f"work-{index}"
            controller = WorkController(work)
            controller.create({"task": {"kind": kind, "index": index}})
            controller.mutate(1, {"task": {"kind": kind, "index": index, "verified": True}})
            result = VerificationRunner(registry).run("check", cwd=work, binding=binding())
            if result.result != "PASS":
                raise RuntimeError(f"pilot verification failed for {kind}: {result.result}")
            completed += 1
        freshness = evaluate_freshness(result, current_contract_digest=digest, current_snapshot=result.artifact["repository_snapshot"], current_registry_digest=registry_digest, current_policy_digest=digest, current_approval_root=result.artifact["approval_root"])
        verdict = converge(analyze([], [], [], []), [result], freshness=freshness, trust=evaluate_trust(result, policy=policy, approval_root=approval_root))
        if verdict.verdict != "CONVERGED":
            raise RuntimeError(f"pilot convergence failed: {verdict.verdict}")
        elapsed = int((time.monotonic() - started) * 1000)
        convergence_elapsed = int((time.monotonic() - convergence_started) * 1000)
    metrics = PilotMetrics(setup_time_ms=elapsed, verification_runtime_ms=elapsed, convergence_runtime_ms=convergence_elapsed)
    return {"work_items": len(kinds), "completed": completed, "kinds": kinds, "metrics": metrics.__dict__, "external_harness": False}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
