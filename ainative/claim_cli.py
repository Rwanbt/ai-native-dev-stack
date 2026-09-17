"""The `ainative claim-attempt` recovery surface: list, inspect, abandon.

Recovery is an operator act, so the surface is read-mostly: listing and
inspecting never change anything, and abandoning is one explicit transition
that requires `--confirm`. There is deliberately no "retry" here — an
uncertain POST is resolved by searching the remote for the attempt marker,
never by posting again (ADR-0018 section 6).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import claims
from .cli_support import project_from, report as _report


def add_claim_parser(commands) -> None:
    claim = commands.add_parser(
        "claim-attempt", help="Inspect or abandon journaled claim attempts.")
    subcommands = claim.add_subparsers(dest="claim_command", required=True)
    listing = subcommands.add_parser("list", help="Every journaled claim attempt.")
    _common(listing)
    inspect = subcommands.add_parser("inspect", help="One attempt, in full.")
    inspect.add_argument("attempt_id")
    _common(inspect)
    abandon = subcommands.add_parser(
        "abandon", help="Give up an unresolved attempt (local transition only).")
    abandon.add_argument("attempt_id")
    abandon.add_argument("--confirm", action="store_true",
                         help="required: this is an operator decision")
    _common(abandon)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=Path, default=None,
                        help="project root (default: the current directory)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _attempt_text(attempt: claims.ClaimAttempt) -> str:
    lines = [f"{attempt.attempt_id}: {attempt.state}",
             f"  authority: {attempt.authority.get('provider')}:"
             f"{attempt.authority.get('project')}",
             f"  item: {attempt.item}",
             f"  principal: {attempt.principal}",
             f"  marker: {attempt.marker}",
             f"  created: {attempt.created_at}"]
    if attempt.outcome_at:
        lines.append(f"  outcome: {attempt.outcome_at}")
    if attempt.note:
        lines.append(f"  note: {attempt.note}")
    return "\n".join(lines)


def run_claim_command(args: argparse.Namespace) -> int:
    project = project_from(args)
    if args.claim_command == "list":
        attempts = claims.list_attempts(project)
        record = {"attempts": [attempt.to_record() for attempt in attempts],
                  "unresolved": [attempt.attempt_id for attempt in attempts
                                 if attempt.state in claims.UNRESOLVED]}
        lines = [f"{len(attempts)} attempt(s), {len(record['unresolved'])} unresolved"]
        for attempt in attempts:
            lines.append(f"  {attempt.state:<10} {attempt.attempt_id}  "
                         f"item {attempt.item}")
        return _report(args, record, "\n".join(lines))
    if args.claim_command == "inspect":
        attempt = claims.load_attempt(project, args.attempt_id)
        return _report(args, attempt.to_record(), _attempt_text(attempt))
    attempt = claims.abandon(project, args.attempt_id, confirm=args.confirm)
    return _report(args, attempt.to_record(), _attempt_text(attempt))


__all__ = ["add_claim_parser", "run_claim_command"]
