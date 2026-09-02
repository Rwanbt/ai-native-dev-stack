"""Thin developer facade over the deterministic core.

Every subcommand parses arguments, loads JSON, and calls a core API. No
decision is made here: a verdict printed by this module is the one the engine
returned, and the process exit code is its documented mapping.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .controller import WorkController
from .convergence import VERDICT_EXIT_CODES, converge
from .evidence import VerificationEvidence
from .freshness import FreshnessResult, evaluate_freshness
from .runner import VerificationRunner
from .traceability import analyze
from .trust import TrustVerdict, evaluate_trust


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

    verify = commands.add_parser("verify")
    verify.add_argument("--registry", type=Path, required=True)
    verify.add_argument("--binding", type=Path, required=True)
    verify.add_argument("--command", required=True)
    verify.add_argument("--cwd", type=Path, default=Path.cwd())
    verify.add_argument("--runs-dir", type=Path)
    verify.add_argument("--require-substance", action="store_true")

    decide = commands.add_parser("converge")
    decide.add_argument("--contract", type=Path, required=True)
    decide.add_argument("--evidence", type=Path, action="append", default=[])
    decide.add_argument("--freshness", type=Path)
    decide.add_argument("--policy", type=Path)
    decide.add_argument("--approval-root", type=Path)
    decide.add_argument("--waiver", type=Path, action="append", default=[])
    decide.add_argument("--approval", type=Path, action="append", default=[])
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
    runner = VerificationRunner(_load(args.registry), runs_dir=args.runs_dir)
    evidence = runner.run(args.command, cwd=args.cwd, binding=_load(args.binding), require_substance=args.require_substance)
    _emit(evidence.to_record())
    return 0 if evidence.result == "PASS" else 1


def _freshness(path: Path | None, evidence: list[VerificationEvidence]) -> FreshnessResult | None:
    """Evaluate freshness from declared current identities, or not at all."""

    if path is None or not evidence:
        return None
    current = _load(path)
    return evaluate_freshness(
        evidence[0],
        current_contract_digest=current["contract_digest"],
        current_snapshot=current["repository_snapshot"],
        current_registry_digest=current["command_registry_digest"],
        current_policy_digest=current["policy_digest"],
        current_approval_root=current["approval_root"],
        current_specification_digest=current.get("verification_specification_digest"),
        current_head=current.get("snapshot_head"),
    )


def _trust(policy_path: Path | None, root_path: Path | None, evidence: list[VerificationEvidence]) -> TrustVerdict | None:
    if policy_path is None or root_path is None or not evidence:
        return None
    return evaluate_trust(evidence[0], policy=_load(policy_path), approval_root=_load(root_path))


def _converge(args: argparse.Namespace) -> int:
    contract = _load(args.contract)
    graph = analyze(
        contract.get("requirements", []),
        contract.get("acceptance_criteria", []),
        contract.get("tasks", []),
        contract.get("verification_specifications", []),
    )
    evidence = [VerificationEvidence(_load(path)) for path in args.evidence]
    verdict = converge(
        graph,
        evidence,
        freshness=_freshness(args.freshness, evidence),
        trust=_trust(args.policy, args.approval_root, evidence),
        policy=_load(args.policy) if args.policy else None,
        waivers=[_load(path) for path in args.waiver],
        human_approvals=[_load(path) for path in args.approval],
    )
    _emit({"verdict": verdict.verdict, "reason": verdict.reason, "fingerprint": verdict.fingerprint, "gaps": [{"code": gap.code, "uid": gap.uid, "detail": gap.detail} for gap in verdict.gaps]})
    return VERDICT_EXIT_CODES[verdict.verdict]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.entrypoint == "work":
        return _work(args)
    if args.entrypoint == "verify":
        return _verify(args)
    return _converge(args)


__all__ = ["build_parser", "main"]
