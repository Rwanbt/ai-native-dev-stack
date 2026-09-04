"""Measure real work items through the authoritative production surface.

This is an instrument, not a source of work. It does not create contracts, does
not invent items, and cannot make a pilot pass. Given a plan naming governed
work directories that a real harness has actually worked on, it runs each one
through `evaluate_work()` and records what happened.

Three properties it is built to have, because the harness it replaces had none
of them:

- **no authority is injected.** It never constructs a `TrustVerdict`, a
  `FreshnessResult`, a `VerificationEvidence`, a policy or a root, and never
  calls the pure `converge()` kernel. The only verdict it reports is the one
  the production boundary returned. `tests/test_workplane_pilot.py` asserts
  this structurally, because a comment saying so is not a guarantee;
- **measured and declared are separated.** Whether a verdict was *correct* is
  not observable from inside: it needs someone who knows what the work was
  supposed to do. So the plan declares expectations and friction up front, the
  instrument measures what it can see, and the record keeps the two apart. A
  field the instrument cannot establish is never quietly filled in;
- **it refuses to call itself pilot evidence** unless the plan actually meets
  the protocol: five real items across the five kinds, through at least two
  distinct harnesses, with nothing synthetic and no harness error. Otherwise the
  record says `pilot_evidence: false` and lists exactly why. The gate cannot be
  closed by running this script with a convenient plan.

`--self-check` builds one governed work and measures it, to prove the
instrument works. That output is labelled `pilot_evidence: false` and is not
evidence about anything except the instrument.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative_workplane.contracts import NORMATIVE_ARTIFACTS
from ainative_workplane.controller import ControllerError, WorkController
from ainative_workplane.evaluator import EvaluationError, establish_authority, evaluate_work

# The protocol this instrument measures against. Section 48: two features, a
# bugfix, a refactor and a hotfix, through at least two real AI harnesses.
REQUIRED_KINDS = ("feature", "feature", "bugfix", "refactor", "hotfix")
REQUIRED_HARNESSES = 2


@dataclass(frozen=True)
class PilotItem:
    """One real piece of work, and what the operator declared about it."""

    kind: str
    harness_id: str
    work_dir: Path
    repository_root: Path
    provider: str | None = None
    synthetic: bool = False
    declared: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: Any) -> "PilotItem":
        if not isinstance(raw, dict):
            raise ValueError("each item must be an object")
        missing = [name for name in ("kind", "harness_id", "work_dir", "repository_root") if not raw.get(name)]
        if missing:
            raise ValueError(f"item is missing {', '.join(missing)}")
        return cls(
            kind=str(raw["kind"]),
            harness_id=str(raw["harness_id"]),
            work_dir=Path(raw["work_dir"]),
            repository_root=Path(raw["repository_root"]),
            provider=raw.get("provider"),
            synthetic=bool(raw.get("synthetic", False)),
            declared=dict(raw.get("declared", {})),
        )


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, check=False, timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ""


def _normative_digest_at(controller: WorkController, revision: int) -> str | None:
    """The success conditions one committed revision carried."""

    directory = controller.revisions / str(revision)
    if not directory.is_dir():
        return None
    artifacts: dict[str, Any] = {}
    for name in sorted(NORMATIVE_ARTIFACTS):
        candidate = directory / f"{name}.json"
        if candidate.is_file():
            try:
                artifacts[name] = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return controller.normative_digest(artifacts)


def _normative_mutations(controller: WorkController, revisions: int) -> int:
    """How many committed revisions changed the success conditions.

    Each one needed an approval to be written at all, so this is the count of
    approvals the work actually required -- derived from committed state rather
    than from counting files someone may have kept anywhere.
    """

    changes = 0
    previous = _normative_digest_at(controller, 1)
    for revision in range(2, revisions + 1):
        current = _normative_digest_at(controller, revision)
        if current is not None and current != previous:
            changes += 1
        previous = current if current is not None else previous
    return changes


def _recorded_runtime_ms(work_dir: Path, since: float) -> int | None:
    """Total runtime of the verifications this measurement produced.

    Read from the local execution log, which is not authority and is never an
    input to a verdict -- here it is the only place the per-run durations exist,
    and a duration cannot change what was decided.
    """

    runs = work_dir / "runs"
    if not runs.is_dir():
        return None
    total = 0
    seen = False
    for path in runs.glob("*.json"):
        if path.stat().st_mtime < since:
            continue
        try:
            total += int(json.loads(path.read_text(encoding="utf-8")).get("duration_ms", 0))
            seen = True
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return total if seen else None


def measure(item: PilotItem) -> dict[str, Any]:
    """Run one governed work through the production boundary and record it."""

    record: dict[str, Any] = {
        "kind": item.kind,
        "harness_id": item.harness_id,
        "provider": item.provider,
        "synthetic": item.synthetic,
        "work_dir": str(item.work_dir),
        "declared": item.declared,
        "harness_error": None,
    }
    try:
        controller = WorkController(item.work_dir)
        before = controller.read()
        context = establish_authority(item.work_dir, item.repository_root)
        started_at = time.time()
        started = time.monotonic()
        evaluation = evaluate_work(item.work_dir, item.repository_root)
        wall_ms = int((time.monotonic() - started) * 1000)
        after, artifacts = controller.load_committed_artifacts()
        record["work_uid"] = after["work_uid"]
        record["measured"] = {
            "verdict": evaluation.verdict.verdict,
            "reason": evaluation.verdict.reason,
            "gaps": [{"code": gap.code, "uid": gap.uid, "detail": gap.detail} for gap in evaluation.verdict.gaps],
            "authority_established": context.established,
            "authority_refusal": None if context.established else context.refusal,
            "verification_specifications": len(context.specifications),
            "verification_runs": len(evaluation.assessments),
            "eligible_runs": sum(1 for assessment in evaluation.assessments if assessment.eligible),
            "verification_runtime_ms": _recorded_runtime_ms(item.work_dir, started_at),
            "convergence_wall_ms": wall_ms,
            "contract_revisions": after["revision"],
            "normative_mutations": _normative_mutations(controller, after["revision"]),
            "root_transitions": len(controller.root_transitions()),
            "contract_digest": evaluation.contract_digest,
            "contract_intact": before["revision"] == after["revision"] and controller.normative_digest(artifacts) == _normative_digest_at(controller, after["revision"]),
            "evidence_provenance": evaluation.provenance.to_record(),
            "authority_provenance": evaluation.authority_provenance.to_record(),
            "repository_head": _git(item.repository_root, "rev-parse", "HEAD"),
            "repository_dirty": bool(_git(item.repository_root, "status", "--porcelain")),
        }
    except (EvaluationError, ControllerError, OSError, ValueError) as error:
        record["harness_error"] = f"{type(error).__name__}: {error}"
        return record

    expected = item.declared.get("expected_verdict")
    verdict = record["measured"]["verdict"]
    record["assessed"] = {
        "expected_verdict": expected,
        "verdict_matches_expectation": None if expected is None else verdict == expected,
        # A false CONVERGED is the one that matters: the engine said the work
        # was done when the operator says it was not.
        "false_converged": bool(expected and verdict == "CONVERGED" and expected != "CONVERGED"),
        "false_not_converged": bool(expected == "CONVERGED" and verdict != "CONVERGED"),
    }
    return record


def assess_plan(items: list[PilotItem], records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Decide whether this run is pilot evidence, and say why when it is not."""

    refusals: list[str] = []
    kinds = sorted(item.kind for item in items)
    if kinds != sorted(REQUIRED_KINDS):
        refusals.append(f"the protocol needs {sorted(REQUIRED_KINDS)}, this plan has {kinds}")
    harnesses = {item.harness_id for item in items}
    if len(harnesses) < REQUIRED_HARNESSES:
        refusals.append(f"the protocol needs at least {REQUIRED_HARNESSES} distinct harnesses, this plan has {sorted(harnesses)}")
    synthetic = [item.kind for item in items if item.synthetic]
    if synthetic:
        refusals.append(f"the protocol needs real work items; {len(synthetic)} are declared synthetic")
    failed = [record["kind"] for record in records if record["harness_error"]]
    if failed:
        refusals.append(f"the instrument could not measure {len(failed)} item(s): {failed}")
    missing = [record["kind"] for record in records if record.get("declared", {}).get("expected_verdict") is None]
    if missing:
        refusals.append(f"{len(missing)} item(s) declare no expected verdict, so no false verdict can be detected")
    return not refusals, refusals


def run_plan(plan: dict[str, Any]) -> dict[str, Any]:
    items = [PilotItem.parse(raw) for raw in plan.get("items", [])]
    records = [measure(item) for item in items]
    evidence, refusals = assess_plan(items, records)
    converged = [record for record in records if record.get("measured", {}).get("verdict") == "CONVERGED"]
    return {
        "schema_version": 2,
        "pilot_id": plan.get("pilot_id"),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "surface": "evaluate_work",
        "authority": "production_boundary",
        "pilot_evidence": evidence,
        "pilot_evidence_refusals": refusals,
        "harnesses": sorted({item.harness_id for item in items}),
        "work_items": len(items),
        "converged": len(converged),
        "false_converged": sum(1 for record in records if record.get("assessed", {}).get("false_converged")),
        "false_not_converged": sum(1 for record in records if record.get("assessed", {}).get("false_not_converged")),
        "harness_errors": [record["harness_error"] for record in records if record["harness_error"]],
        "items": records,
    }


def self_check(directory: Path) -> dict[str, Any]:
    """Measure one governed work built here, to prove the instrument works.

    Explicitly not pilot evidence: the item is synthetic, there is one harness,
    and `assess_plan` refuses it on both counts. It exists so a reviewer can see
    the instrument produce a real record from the real production boundary.
    """

    from tests.test_workplane_authority import GovernedWork

    work = GovernedWork(directory)
    plan = {
        "pilot_id": "instrument-self-check",
        "items": [{
            "kind": "feature",
            "harness_id": "self-check",
            "work_dir": str(work.work),
            "repository_root": str(work.repo),
            "synthetic": True,
            "declared": {"expected_verdict": "CONVERGED", "manual_interventions": 0, "friction": None},
        }],
    }
    return run_plan(plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure real work items through the authoritative production surface.")
    parser.add_argument("--plan", type=Path, help="A pilot plan naming governed work directories a real harness has worked on.")
    parser.add_argument("--self-check", action="store_true", help="Measure one governed work built here. Never pilot evidence.")
    parser.add_argument("--output", type=Path, help="Write the record here as well as to stdout.")
    arguments = parser.parse_args(argv)
    if arguments.self_check == bool(arguments.plan):
        parser.error("give exactly one of --plan or --self-check")
    if arguments.self_check:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="workplane-pilot-selfcheck-", ignore_cleanup_errors=True) as directory:
            record = self_check(Path(directory))
    else:
        record = run_plan(json.loads(arguments.plan.read_text(encoding="utf-8")))
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    # A run that measured everything it was asked to measure succeeded, whatever
    # the verdicts were. Only the instrument failing is this script's failure.
    return 1 if record["harness_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
