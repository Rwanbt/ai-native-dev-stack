"""Five-work-item pilot for the V2 core, recorded per item.

Running this proves the engine survives a five-item shape end to end. It does
not prove the section 46-48 pilot: the items are synthetic and one harness is
one harness. The record says which of those it is rather than leaving a reader
to assume, so that two real harnesses producing two records can be compared.
"""

from __future__ import annotations

import argparse
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
from ainative_workplane.trust import approval_root_commitment, evaluate_trust, policy_commitment


def run(harness_id: str = "local", *, provider: str | None = None) -> dict[str, object]:
    registry = {"schema_name": "command_registry", "schema_version": 1, "commands": {"check": {"argv": [sys.executable, "-c", "print('pilot pass')"], "timeout_seconds": 3, "max_output_bytes": 1024}}}
    kinds = ["feature", "feature", "bugfix", "refactor", "hotfix"]
    started = time.monotonic()
    convergence_started = time.monotonic()
    completed = 0
    items: list[dict[str, object]] = []
    registry_digest = canonical_digest(registry)
    digest = "a" * 64
    policy = {"schema_name": "project_policy", "schema_version": 1, "approval_predicate": {"predicate_id": "recorded_owner_ack", "policy_digest": digest}, "required_mutation_facts": {}, "required_evidence_facts": {}, "waiver_approval_rule": {"predicate_id": "recorded_owner_ack", "policy_digest": digest}, "human_approval_rule": {"predicate_id": "recorded_owner_ack", "policy_digest": digest}, "promotion_policy": "explicit"}
    policy_digest = policy_commitment(policy)
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        policy[field]["policy_digest"] = policy_digest
    approval_root = {"schema_name": "approval_root", "schema_version": 1, "uid": generate_uid("root"), "root_digest": digest, "policy_digest": policy_digest, "root_provenance": "LOCAL_UNTRUSTED", "bootstrap": {"initialized_at": "2026-09-02T00:00:00Z", "initialized_by": "pilot"}}
    approval_root["root_digest"] = approval_root_commitment(approval_root)
    specification_uid = generate_uid("verify")
    graph = analyze(
        [{"uid": "req-pilot", "acceptance_criteria": [{"uid": "ac-pilot", "digest": digest}]}],
        [{"uid": "ac-pilot", "requirement": {"uid": "req-pilot", "digest": digest}, "verification_specifications": [{"uid": specification_uid, "digest": digest}]}],
        [{"uid": "task-pilot", "requirements": [{"uid": "req-pilot", "digest": digest}]}],
        [{"uid": specification_uid, "relationship": "black_box", "covered_implementation_paths": ["src/**"], "execution_scope": ["tests/**"]}],
    )

    def binding() -> dict[str, object]:
        reference = lambda prefix: {"uid": generate_uid(prefix), "digest": digest}
        return {"work": reference("work"), "contract_revision": 1, "contract_digest": digest, "verification_specification": {"uid": specification_uid, "digest": digest}, "command_registry_digest": registry_digest, "policy_digest": policy_digest, "approval_root": {"uid": approval_root["uid"], "digest": approval_root["root_digest"]}, "repository_snapshot": reference("snapshot"), "snapshot_content_digest": digest, "snapshot_dependency_digest": digest, "snapshot_head": "0" * 40, "producer": "local-pilot", "producer_version": "1", "evidence_provenance": "LOCAL_UNTRUSTED"}
    with tempfile.TemporaryDirectory(prefix="workplane-pilot-") as directory:
        root = Path(directory)
        for index, kind in enumerate(kinds, 1):
            work = root / f"work-{index}"
            controller = WorkController(work)
            controller.create({"task": {"kind": kind, "index": index}})
            controller.mutate(1, {"task": {"kind": kind, "index": index, "verified": True}})
            item_started = time.monotonic()
            result = VerificationRunner(registry).run("check", cwd=work, binding=binding())
            if result.result != "PASS":
                raise RuntimeError(f"pilot verification failed for {kind}: {result.result}")
            item_verdict = converge(graph, [result], freshness=evaluate_freshness(result, current_contract_digest=digest, current_snapshot=result.artifact["repository_snapshot"], current_registry_digest=registry_digest, current_policy_digest=policy_digest, current_approval_root=result.artifact["approval_root"]), trust=evaluate_trust(result, policy=policy, approval_root=approval_root))
            items.append({
                "kind": kind,
                "harness": harness_id,
                "provider": provider,
                "work_uid": controller.read()["work_uid"],
                "contract_revisions": controller.read()["revision"],
                "verification_runs": 1,
                "reruns": 0,
                "gaps": [gap.code for gap in item_verdict.gaps],
                "stale_invalidations": 0,
                "manual_interventions": 0,
                "duration_ms": int((time.monotonic() - item_started) * 1000),
                "tokens": None,
                "false_positives": 0,
                "false_negatives": 0,
                "friction": None,
                "verdict": item_verdict.verdict,
            })
            completed += 1
        freshness = evaluate_freshness(result, current_contract_digest=digest, current_snapshot=result.artifact["repository_snapshot"], current_registry_digest=registry_digest, current_policy_digest=policy_digest, current_approval_root=result.artifact["approval_root"])
        verdict = converge(graph, [result], freshness=freshness, trust=evaluate_trust(result, policy=policy, approval_root=approval_root))
        if verdict.verdict != "CONVERGED":
            raise RuntimeError(f"pilot convergence failed: {verdict.verdict}")
        elapsed = int((time.monotonic() - started) * 1000)
        convergence_elapsed = int((time.monotonic() - convergence_started) * 1000)
    metrics = PilotMetrics(setup_time_ms=elapsed, verification_runtime_ms=elapsed, convergence_runtime_ms=convergence_elapsed)
    return {
        "schema_version": 1,
        "harness_id": harness_id,
        "provider": provider,
        "work_items": len(kinds),
        "completed": completed,
        "kinds": kinds,
        "items": items,
        "metrics": metrics.__dict__,
        "items_source": "synthetic",
        "external_harness": False,
        "authority": "smoke_pilot_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the five-item smoke pilot and record it per item.")
    parser.add_argument("--harness-id", default="local", help="Which harness ran this, so two records can be compared.")
    parser.add_argument("--provider", help="Model or provider, when the harness has one.")
    parser.add_argument("--output", type=Path, help="Write the record here as well as to stdout.")
    arguments = parser.parse_args()
    record = run(arguments.harness_id, provider=arguments.provider)
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
