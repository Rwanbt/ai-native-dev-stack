"""The `ainative feature` command surface: parser, rendering, transitions.

Split out of `cli.py` for the size budget. The command is self-contained — its
grammar, its status rendering and its transition handler — and the dispatcher
stays the dispatcher. The two rendering callables are injected so this module
never imports `cli` back (which would be a cycle).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from . import features as featureslib
from . import installer
from . import manifest as manifestlib
from . import state as statelib


def add_feature_parser(commands) -> None:
    feature = commands.add_parser("feature",
                                  help="Inspect or change optional project features.")
    feature_commands = feature.add_subparsers(dest="feature_command", required=True)
    status = feature_commands.add_parser("status",
                                         help="Report the effective feature set.")
    _common(status, dry_run=False)
    enable = feature_commands.add_parser("enable", help="Activate a feature.")
    enable.add_argument("target")
    _common(enable)
    disable = feature_commands.add_parser("disable", help="Deactivate a feature.")
    disable.add_argument("target")
    _common(disable)
    switch = feature_commands.add_parser(
        "switch", help="Replace the active work forge ('none' for Generic Git).")
    switch.add_argument("target", help="a feature name, or 'none'")
    _common(switch)


def _common(parser: argparse.ArgumentParser, *, dry_run: bool = True) -> None:
    parser.add_argument("--project", type=Path, default=None,
                        help="project root (default: the current directory)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    if dry_run:
        parser.add_argument("--dry-run", action="store_true",
                            help="print the change plan; touch nothing")
    parser.add_argument("--force-unlock", action="store_true",
                        help="take the lifecycle lock even if another one is recorded")


def status_record(project: Path) -> tuple[dict, str]:
    """The status payload and its text rendering, from the shared projection."""

    distribution = manifestlib.load()
    effective = featureslib.project_install_state(statelib.load(project), distribution)
    active = list(effective.active_features) if effective else []
    record = {
        "installed": effective is not None,
        "active_profile": effective.active_profile if effective else None,
        "active_features": active,
        "projected_from_legacy": bool(effective and effective.projected_from_legacy),
        "declared": {name: {"title": value.title, "work_forge": value.work_forge,
                            "components": list(value.components),
                            "conflicts": list(value.conflicts)}
                     for name, value in sorted(distribution.features.items())},
    }
    lines = [f"Active features: {', '.join(active) or 'none'}"]
    for name in sorted(record["declared"]):
        mark = "*" if name in active else " "
        lines.append(f"  [{mark}] {name} — {record['declared'][name]['title']}")
    if record["projected_from_legacy"]:
        lines.append("  (projected from the V1 state: "
                     f"{featureslib.legacy_default(distribution)} is the "
                     "compatibility default)")
    return record, "\n".join(lines)


def run_feature_command(args: argparse.Namespace, *, project: Path,
                        report: Callable[[dict, str], int],
                        plan_text: Callable[[object], str]) -> int:
    if args.feature_command == "status":
        record, text = status_record(project)
        return report(record, text)

    transition = {"enable": None, "disable": None, "switch_to": None}
    if args.feature_command == "enable":
        transition["enable"] = args.target
    elif args.feature_command == "disable":
        transition["disable"] = args.target
    else:
        transition["switch_to"] = args.target
    result = installer.set_features(project, dry_run=args.dry_run,
                                    force_unlock=args.force_unlock, **transition)
    return report(result.to_record(), plan_text(result))


__all__ = ["add_feature_parser", "run_feature_command", "status_record"]
