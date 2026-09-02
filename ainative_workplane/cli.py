"""PR-06 minimal developer facade over the deterministic core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .controller import WorkController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ainative")
    commands = parser.add_subparsers(dest="command", required=True)
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
    return parser


def _artifacts(values: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        name, separator, payload = value.partition("=")
        if not separator or not name:
            raise ValueError("--artifact requires NAME=JSON")
        result[name] = json.loads(payload)
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = WorkController(args.path)
    if args.work_command == "new":
        manifest = controller.create(_artifacts(args.artifact))
    elif args.work_command == "validate":
        manifest = controller.read()
    else:
        manifest = controller.mutate(args.expected_revision, _artifacts(args.artifact))
    print(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    return 0
