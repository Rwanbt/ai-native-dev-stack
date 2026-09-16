"""`ainative forge detect|status` — observation only.

Zero network, zero credentials, zero writes, zero persistent trust (PR-3,
#164). `detect` answers "what can be seen locally"; `status` adds the effective
feature set and the unresolved claim attempts. A fork renders as AMBIGUOUS and
nothing here prefers origin — the rendering is the diagnostic, the refusal
belongs to the mutation path (ADR-0018).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import observation
from .cli_support import project_from, report as _report


def add_forge_parser(commands) -> None:
    forge = commands.add_parser(
        "forge", help="Observe the project's remotes and work authority.")
    subcommands = forge.add_subparsers(dest="forge_command", required=True)
    detect = subcommands.add_parser(
        "detect", help="Observed remotes and the Work Authority resolution.")
    _common(detect)
    status = subcommands.add_parser(
        "status", help="The forge picture: remotes, resolution, features, claims.")
    _common(status)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=Path, default=None,
                        help="project root (default: the current directory)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def _resolution_line(resolution: dict) -> str:
    authority = resolution.get("authority") or {}
    if authority:
        return (f"Resolution: {resolution['state']} "
                f"{authority.get('provider')}:{authority.get('project')}")
    return f"Resolution: {resolution['state']}"


def detect_text(picture: dict) -> str:
    lines = [f"Git repository: {'yes' if picture['git'] else 'no'}"]
    if picture["remotes"]:
        lines.append("Work authority (observed candidates):")
        for remote in picture["remotes"]:
            lines.append(f"  {remote['name']:<10} {remote['provider']:<8} "
                         f"{remote['project'] or '-':<24} {remote['url']}")
    else:
        lines.append("Work authority (observed candidates): none")
    lines.append(_resolution_line(picture["resolution"]))
    if picture["resolution"].get("detail"):
        lines.append(f"  {picture['resolution']['detail']}")
    return "\n".join(lines)


def status_text(view: dict) -> str:
    features = view["features"]
    summary = view["claim_attempts"]
    lines = ["Active features: " + (", ".join(features["active"]) or "none")
             + ("  (projected from the V1 state)" if features["projected_from_legacy"]
                else "")]
    if summary["journal"] == "ok":
        lines.append(f"Unresolved claim attempts: {len(summary['unresolved'])}")
    else:
        lines.append(f"Unresolved claim attempts: journal unavailable "
                     f"({summary['detail']})")
    lines.append("")
    lines.append(detect_text(view["forge"]))
    return "\n".join(lines)


def run_forge_command(args: argparse.Namespace) -> int:
    project = project_from(args)
    if args.forge_command == "detect":
        picture = observation.forge_picture(project)
        return _report(args, picture, detect_text(picture))
    view = observation.project_view(project)
    return _report(args, view, status_text(view))


__all__ = ["add_forge_parser", "run_forge_command", "detect_text", "status_text"]
