"""Thin developer facade over the deterministic core.

Every subcommand parses arguments, loads JSON, and calls a core API. No
decision is made here: a verdict printed by this module is the one the engine
returned, and the process exit code is its documented mapping.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .controller import WorkController
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

    work = commands.add_parser("work")
    work_commands = work.add_subparsers(dest="work_command", required=True)
    new = work_commands.add_parser("new")
    new.add_argument("path", type=Path)
    new.add_argument("--artifact", action="append", default=[])
    validate = work_commands.add_parser("validate")
    validate.add_argument("path", type=Path)
    update = work_commands.add_parser("update")
    update.add_argument("path", type=Path)
    update.add_argument("expected_revision", type=int)
    update.add_argument("--artifact", action="append", default=[])

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
    loose = debug_commands.add_parser("run-command")
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


def _work(args: argparse.Namespace) -> int:
    controller = WorkController(args.path)
    if args.work_command == "new":
        manifest = controller.create(_artifacts(args.artifact))
    elif args.work_command == "validate":
        manifest = controller.read()
    else:
        manifest = controller.mutate(args.expected_revision, _artifacts(args.artifact))
    _emit(manifest)
    return 0


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
        if args.entrypoint == "verify":
            return _verify(args)
        if args.entrypoint == "debug":
            return _debug_run_command(args)
        return _converge(args)
    except EvaluationError as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main"]
