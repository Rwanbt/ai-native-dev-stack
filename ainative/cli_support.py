"""Small shared plumbing for the `ainative` command modules.

Split out so `cli.py` stays the dispatcher and the command modules
(`feature_cli`, `claim_cli`, `forge_cli`) render the same way without
importing `cli` back — which would be a cycle. Nothing here imports the
lifecycle or the Work Plane: it is argparse, JSON and a path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .lifecycle.errors import EXIT_OK

# What the plan says, as opposed to what the journal records. `BLOCK_WRITE`
# read to a user as "blocked" while the operation actually proceeded; the
# internal names stay stable for journals, the labels must not lie.
ACTION_LABELS = {
    "CREATE": "create",
    "REPLACE": "replace",
    "REMOVE": "remove",
    "SKIP": "skip",
    "PRESERVE": "preserve",
    "CONFLICT": "conflict",
    "REGION_WRITE": "configure-region",
    "REGION_REMOVE": "remove-region",
    "HOOK_WRITE": "configure-hook",
    "HOOK_REMOVE": "remove-hook",
    "BLOCK_WRITE": "configure-region",
    "BLOCK_REMOVE": "remove-region",
}


def emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def project_from(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "project", None) or Path.cwd())


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action.lower())


def report(args: argparse.Namespace, record: dict, text: str) -> int:
    if getattr(args, "json", False):
        emit(record)
    else:
        print(text)
    return EXIT_OK


def plan_text(result) -> str:
    plan = result.plan
    header = "(dry-run — nothing was written)\n" if result.dry_run else ""
    counts = ", ".join(f"{action_label(action)} {count}"
                       for action, count in sorted(plan.counts().items())) or "no changes"
    lines = [f"{header}{plan.operation}: {plan.from_profile or 'none'} -> "
             f"{plan.to_profile or 'none'}", f"  {counts}"]
    for change in plan.changes:
        if change.action in ("SKIP",) and not result.dry_run:
            continue
        lines.append(f"  {action_label(change.action):<18} {change.path}"
                     + (f"   ({change.reason})" if change.reason else ""))
    for notice in result.notices:
        lines.append("")
        lines.append(notice)
    return "\n".join(lines)


__all__ = ["ACTION_LABELS", "emit", "project_from", "action_label", "report", "plan_text"]
