"""Thin developer facade over the deterministic core.

Every subcommand parses arguments, loads JSON, and calls a core API. No
decision is made here: a verdict printed by this module is the one the engine
returned, and the process exit code is its documented mapping.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bootstrap import BootstrapError, anchor_refusal, bootstrap, creation_approval_path, load as load_trust_anchor, locate as locate_trust_anchor, verified_anchor
from .contracts import ContractError, generate_uid
from .controller import ControllerError, WorkController
from .convergence import VERDICT_EXIT_CODES
from .evaluator import EvaluationError, evaluate_work, run_verification
from .runner import VerificationRunner


def _load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ainative")
    commands = parser.add_subparsers(dest="entrypoint", required=True)

    work = commands.add_parser("work", help="Create, read, and mutate a committed work contract under a recorded approval.")
    work_commands = work.add_subparsers(dest="work_command", required=True)
    new = work_commands.add_parser("new", help="Create a new work contract at PATH.")
    new.add_argument("path", type=Path)
    new.add_argument("--artifact", action="append", default=[])
    admit = work_commands.add_parser("admit", help="Approve creating a work at PATH, before the contract exists. Binds the project's trust anchor to the exact genesis the contract will carry.")
    admit.add_argument("path", type=Path)
    admit.add_argument("--artifact", action="append", default=[], help="The same artifacts `work new` will be given; the approval binds their digest.")
    admit.add_argument("--by", required=True, help="Who is approving this work's creation.")
    admit.add_argument("--repo", type=Path, default=Path("."))
    validate = work_commands.add_parser("validate", help="Read a work contract at PATH and emit its manifest.")
    validate.add_argument("path", type=Path)
    update = work_commands.add_parser("update", help="Apply a recorded mutation approval to update a work contract at PATH.")
    update.add_argument("path", type=Path)
    update.add_argument("expected_revision", type=int)
    update.add_argument("--artifact", action="append", default=[])
    update.add_argument("--delete", action="append", default=[], help="Name an artifact to remove; nothing disappears implicitly.")
    update.add_argument("--approval", type=Path, help="Path to the recorded mutation_approval authorizing this exact next state.")

    trust = commands.add_parser("trust", help="Pin what a project trusts, before any work contract exists. PRIVILEGED: see ADR-0006.")
    trust_commands = trust.add_subparsers(dest="trust_command", required=True)
    initialize = trust_commands.add_parser("bootstrap", help="Establish the project trust anchor. PRIVILEGED trust-establishment: the Work Plane cannot verify who performed it, so a controlled agent must not be given authority to run it. Refuses to replace an existing anchor.")
    initialize.add_argument("--repo", type=Path, default=Path.cwd())
    initialize.add_argument("--approval-root", type=Path, required=True)
    initialize.add_argument("--policy", type=Path, required=True)
    initialize.add_argument("--by", required=True, help="Who is bootstrapping this project.")
    initialize.add_argument("--predicate", default="signature", help="The predicate the anchor itself must satisfy.")
    initialize.add_argument("--signer", action="append", default=[], help="A key fingerprint this project authorizes to approve. Required in practice under --predicate signature: Git verifying a signature is not this project authorizing the signer.")
    show = trust_commands.add_parser("show", help="Report the anchor governing a location, if any.")
    show.add_argument("--repo", type=Path, default=Path.cwd())

    verify = commands.add_parser("verify", help="Run one committed verification and record bound evidence.")
    verify.add_argument("--work", type=Path, required=True)
    verify.add_argument("--verification", required=True)
    verify.add_argument("--repo", type=Path, default=Path.cwd())

    decide = commands.add_parser("converge", help="Decide convergence from committed authority and the checkout.")
    decide.add_argument("--work", type=Path, required=True)
    decide.add_argument("--repo", type=Path, default=Path.cwd())

    # Loose-file entry points, kept for debugging and explicitly not
    # authoritative: everything they evaluate comes from the caller.
    debug = commands.add_parser("debug", help="Non-authoritative helpers. Never a production verdict.")
    debug_commands = debug.add_subparsers(dest="debug_command", required=True)
    loose = debug_commands.add_parser("run-command", help="Run a verification command against caller-supplied files. Non-authoritative: never a production verdict.")
    loose.add_argument("--registry", type=Path, required=True)
    loose.add_argument("--binding", type=Path, required=True)
    loose.add_argument("--command", required=True)
    loose.add_argument("--cwd", type=Path, default=Path.cwd())
    loose.add_argument("--runs-dir", type=Path)
    loose.add_argument("--require-substance", action="store_true")
    return parser


def _artifacts(values: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        name, separator, payload = value.partition("=")
        if not separator or not name:
            raise ValueError("--artifact requires NAME=JSON")
        result[name] = json.loads(payload)
    return result


def _admit(args: argparse.Namespace) -> int:
    """Write the approval that lets a work be created at all.

    Without this the documented flow has a hole: `trust bootstrap` establishes
    the anchor and `work new` refuses an unadmitted genesis, and nothing shipped
    could produce what sits between them. See EMP-003.
    """

    located = verified_anchor(args.repo)
    if located is None:
        raise BootstrapError(f"PROJECT_TRUST_UNVERIFIED:{anchor_refusal(args.repo)}")
    _, anchor = located
    approval = {
        "schema_name": "work_creation_approval", "schema_version": 1,
        "uid": generate_uid("approval"),
        "trust_uid": anchor["uid"], "trust_digest": anchor["trust_digest"],
        "genesis_digest": WorkController(args.path).normative_digest(_artifacts(args.artifact)),
        "predicate_id": anchor["bootstrap_predicate"]["predicate_id"],
        "approved_by": args.by,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    path = creation_approval_path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    _emit({"approval": str(path), "work_creation_approval": approval})
    return 0


def _work(args: argparse.Namespace) -> int:
    if args.work_command == "admit":
        return _admit(args)
    controller = WorkController(args.path)
    if args.work_command == "new":
        manifest = controller.create(_artifacts(args.artifact))
    elif args.work_command == "validate":
        manifest = controller.read()
    else:
        manifest = controller.mutate(args.expected_revision, _artifacts(args.artifact), delete_artifacts=args.delete, approval=args.approval)
    _emit(manifest)
    return 0


def _trust(args: argparse.Namespace) -> int:
    if args.trust_command == "bootstrap":
        path = bootstrap(args.repo, approval_root=_load(args.approval_root), policy=_load(args.policy), initialized_by=args.by, predicate_id=args.predicate, authorized_signers=args.signer)
        # Labelled, because everything downstream derives its authority from
        # this one act and the runtime cannot verify who performed it.
        _emit({"authority": "privileged_trust_establishment", "anchor": str(path), "trust": load_trust_anchor(path)})
        return 0
    located = locate_trust_anchor(args.repo)
    if located is None:
        _emit({"anchor": None, "governed": False})
        return 1
    anchor = load_trust_anchor(located)
    unverified = anchor_refusal(located, anchor)
    _emit({"anchor": str(located), "governed": unverified is None, "refusal": unverified, "trust": anchor})
    return 0 if unverified is None else 1


def _verify(args: argparse.Namespace) -> int:
    evidence = run_verification(args.work, args.repo, args.verification)
    _emit(evidence.to_record())
    return 0 if evidence.result == "PASS" else 1


def _debug_run_command(args: argparse.Namespace) -> int:
    """Run a command against caller-supplied files. Not authority."""

    runner = VerificationRunner(_load(args.registry), runs_dir=args.runs_dir)
    evidence = runner.run(args.command, cwd=args.cwd, binding=_load(args.binding), require_substance=args.require_substance)
    _emit({"authority": "none", "record": evidence.to_record()})
    return 0 if evidence.result == "PASS" else 1


def _converge(args: argparse.Namespace) -> int:
    evaluation = evaluate_work(args.work, args.repo)
    verdict = evaluation.verdict
    _emit({
        "verdict": verdict.verdict,
        "reason": verdict.reason,
        "fingerprint": verdict.fingerprint,
        "contract_digest": evaluation.contract_digest,
        "observed_provenance": evaluation.provenance.to_record(),
        "authority_provenance": evaluation.authority_provenance.to_record(),
        "gaps": [{"code": gap.code, "uid": gap.uid, "detail": gap.detail} for gap in verdict.gaps],
        "evidence": [
            {"uid": assessment.evidence_uid, "verification_specification": assessment.verification_spec_uid, "eligible": assessment.eligible, "reasons": list(assessment.reasons)}
            for assessment in evaluation.assessments
        ],
    })
    return VERDICT_EXIT_CODES[verdict.verdict]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.entrypoint == "work":
            return _work(args)
        if args.entrypoint == "trust":
            return _trust(args)
        if args.entrypoint == "verify":
            return _verify(args)
        if args.entrypoint == "debug":
            return _debug_run_command(args)
        return _converge(args)
    except (EvaluationError, ControllerError, BootstrapError, ContractError, json.JSONDecodeError, OSError, ValueError) as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main"]
