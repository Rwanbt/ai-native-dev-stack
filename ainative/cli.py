"""`ainative` — one entry point for the lifecycle and the Verified Work Plane.

The dispatcher routes by first token and imports nothing it does not need. That
is not a micro-optimisation: `ainative_workplane` is loaded only inside the
Verified branch, so a Standard install never pulls in an authority module
(ADR-0009 §1), and no lifecycle command can be reached from a verdict-producing
one — which is also why an authority command can never trigger a network update
check (ADR-0009 §6).

Every mutation takes `--dry-run`; every confirmation takes `--yes`; every
command that a script would parse takes `--json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .lifecycle.errors import EXIT_FAILED, EXIT_INVALID_REQUEST, EXIT_OK, LifecycleError

# Routed to the Verified Work Plane, unchanged. Their exit codes and output are
# the Work Plane's contract and are not reinterpreted here.
VERIFIED_COMMANDS = ("trust", "work", "verify", "converge", "debug")

PROFILE_PROMPT = """Choose an AI Native profile:

1. Standard
   Context, memory, skills and AI-native tooling.
   Recommended for learning, personal development and normal AI-assisted work.

2. Verified
   Standard + governed Work Contracts and deterministic verification.
   Recommended for production, teams and autonomous agents.
"""


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _project(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "project", None) or Path.cwd())


def _add_common(parser: argparse.ArgumentParser, *, dry_run: bool = True,
                yes: bool = False) -> None:
    parser.add_argument("--project", type=Path, default=None,
                        help="project root (default: the current directory)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    if dry_run:
        parser.add_argument("--dry-run", action="store_true",
                            help="print the change plan; touch nothing")
    if yes:
        parser.add_argument("--yes", action="store_true",
                            help="confirm without a prompt (required without a TTY)")
    parser.add_argument("--force-unlock", action="store_true",
                        help="take the lifecycle lock even if another one is recorded")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ainative",
        description="AI Native Dev Stack — install, switch profile, update, verify.")
    parser.add_argument("--version", action="store_true", help="print versions and exit")
    commands = parser.add_subparsers(dest="command")

    init = commands.add_parser("init", help="Install the stack into this project.")
    init.add_argument("--profile", choices=("standard", "verified"), default=None,
                      help="skip the prompt and install this profile")
    _add_common(init)

    profile = commands.add_parser("profile", help="Inspect or change the active profile.")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_status = profile_commands.add_parser("status", help="Report the active profile.")
    _add_common(profile_status, dry_run=False)
    switch = profile_commands.add_parser("switch", help="Move to another profile.")
    switch.add_argument("target", choices=("standard", "verified"))
    _add_common(switch)
    purge = profile_commands.add_parser(
        "purge", help="Delete one profile's data. Never implied by `switch`.")
    purge.add_argument("target", choices=("verified",))
    _add_common(purge, yes=True)

    status = commands.add_parser("status", help="What is installed, and its health.")
    status.add_argument("--check-updates", action="store_true",
                        help="also consult the release source (network)")
    _add_common(status, dry_run=False)

    doctor = commands.add_parser("doctor", help="Diagnose. Changes nothing.")
    doctor.add_argument("--check-updates", action="store_true")
    _add_common(doctor, dry_run=False)

    repair = commands.add_parser("repair", help="Fix what doctor reports.")
    _add_common(repair)

    uninstall = commands.add_parser("uninstall", help="Remove the stack; keep your work.")
    uninstall.add_argument("--purge", action="store_true",
                           help="also delete AI Native data roots (irreversible)")
    _add_common(uninstall, yes=True)

    update = commands.add_parser("update", help="Detect and apply a new release.")
    update_commands = update.add_subparsers(dest="update_command")
    update_check = update_commands.add_parser("check", help="Is a newer release available?")
    update_check.add_argument("--force", action="store_true", help="ignore the cache")
    _add_common(update_check, dry_run=False)
    update_rollback = update_commands.add_parser(
        "rollback", help="Restore the project assets the last update replaced.")
    _add_common(update_rollback)
    _add_common(update)
    update.add_argument("--force", action="store_true",
                        help="apply even when the check reports no newer release")

    for name in VERIFIED_COMMANDS:
        commands.add_parser(name, add_help=False,
                            help=f"Verified Work Plane: `ainative {name} --help`.")
    return parser


# --- lifecycle commands ---------------------------------------------------


def _choose_profile(args: argparse.Namespace) -> str:
    if args.profile:
        return args.profile
    if not sys.stdin.isatty():
        raise LifecycleError(
            "PROFILE_INVALID",
            "no profile given and no terminal to ask on. "
            "Use `ainative init --profile standard` or `--profile verified`.")
    print(PROFILE_PROMPT)
    while True:
        answer = input("Profile [1/2] (1): ").strip().lower() or "1"
        if answer in ("1", "standard"):
            return "standard"
        if answer in ("2", "verified"):
            return "verified"
        print("Enter 1 for Standard or 2 for Verified.")


def _report(args: argparse.Namespace, record: dict, text: str) -> int:
    if getattr(args, "json", False):
        _emit(record)
    else:
        print(text)
    return EXIT_OK


def _plan_text(result) -> str:
    plan = result.plan
    header = "(dry-run — nothing was written)\n" if result.dry_run else ""
    counts = ", ".join(f"{action.lower()} {count}"
                       for action, count in sorted(plan.counts().items())) or "no changes"
    lines = [f"{header}{plan.operation}: {plan.from_profile or 'none'} -> "
             f"{plan.to_profile or 'none'}", f"  {counts}"]
    for change in plan.changes:
        if change.action in ("SKIP",) and not result.dry_run:
            continue
        lines.append(f"  {change.action:<12} {change.path}"
                     + (f"   ({change.reason})" if change.reason else ""))
    for notice in result.notices:
        lines.append("")
        lines.append(notice)
    return "\n".join(lines)


def _cmd_init(args: argparse.Namespace) -> int:
    from .lifecycle import installer

    profile = _choose_profile(args)
    result = installer.install(_project(args), profile, dry_run=args.dry_run,
                               force_unlock=args.force_unlock)
    return _report(args, result.to_record(), _plan_text(result))


def _cmd_profile(args: argparse.Namespace) -> int:
    from .lifecycle import installer, status as statuslib, uninstaller

    project = _project(args)
    if args.profile_command == "status":
        report = statuslib.build(project)
        return _report(args, {"profile": report.active_profile,
                              "previous_profile": report.previous_profile,
                              "installed": report.installed,
                              "components": report.components,
                              "verified": report.verified},
                       report.render())
    if args.profile_command == "switch":
        result = installer.switch(project, args.target, dry_run=args.dry_run,
                                  force_unlock=args.force_unlock)
        return _report(args, result.to_record(), _plan_text(result))

    result = uninstaller.purge_profile(project, args.target, dry_run=args.dry_run,
                                       assume_yes=args.yes,
                                       interactive=_confirm_purge(args, project),
                                       force_unlock=args.force_unlock)
    return _report(args, result.to_record(), _uninstall_text(result))


def _confirm_purge(args: argparse.Namespace, project: Path) -> bool:
    """Interactive confirmation. Without a TTY this is always False, so `--yes`
    is the only way through — no CI ever blocks on a prompt."""

    if args.yes or args.dry_run or not sys.stdin.isatty():
        return False
    from .lifecycle import uninstaller, manifest as manifestlib, state as statelib

    state = statelib.load(project)
    if state is None:
        return False
    distribution = manifestlib.load()
    preview = uninstaller.purge_profile(project, getattr(args, "target", "verified"),
                                        dry_run=True, distribution=distribution)
    if not preview.removed:
        return False
    print("The following paths will be permanently deleted:")
    for path in sorted(preview.removed):
        print(f"  {path}")
    return input("Delete them? [y/N]: ").strip().lower() in ("y", "yes")


def _uninstall_text(result) -> str:
    header = "(dry-run — nothing was written)\n" if result.dry_run else ""
    lines = [f"{header}Removed: {len(result.removed)}",
             f"Preserved user-modified: {len(result.preserved_user_modified)}",
             f"Preserved user-data: {len(result.preserved_user_data)}"]
    for path in sorted(result.removed):
        lines.append(f"  REMOVE     {path}")
    for path in sorted(result.preserved_user_modified + result.preserved_user_data):
        lines.append(f"  PRESERVE   {path}")
    return "\n".join(lines)


def _cmd_status(args: argparse.Namespace) -> int:
    from .lifecycle import status as statuslib

    report = statuslib.build(_project(args), check_updates=args.check_updates)
    if args.json:
        _emit(report.to_record())
    else:
        print(report.render())
    return EXIT_OK if report.healthy else EXIT_FAILED


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .lifecycle import recovery

    diagnosis = recovery.diagnose(_project(args), check_updates=args.check_updates)
    if args.json:
        _emit(diagnosis.to_record())
    else:
        print(f"Project: {diagnosis.project}")
        print(f"Installed: {diagnosis.installed}   Profile: {diagnosis.active_profile}")
        print(f"Health: {'healthy' if diagnosis.healthy else 'needs attention'}")
        for item in diagnosis.findings:
            if item["status"] != recovery.OK:
                print(f"  {item['status']:<14} {item['path']}  {item['detail']}")
        for item in diagnosis.transactions:
            print(f"  INTERRUPTED    {item['id']} ({item['operation']}) — run `ainative repair`")
        for note in diagnosis.notes:
            print(f"  note: {note}")
    return EXIT_OK if diagnosis.healthy else EXIT_FAILED


def _cmd_repair(args: argparse.Namespace) -> int:
    from .lifecycle import recovery

    result = recovery.repair(_project(args), dry_run=args.dry_run,
                             force_unlock=args.force_unlock)
    text = "\n".join([
        "(dry-run — nothing was written)" if result.dry_run else "repair complete",
        f"  recovered transactions: {len(result.recovered)}",
        f"  restored files:         {len(result.reinstalled)}",
        f"  dropped stale records:  {len(result.dropped)}",
        f"  preserved user edits:   {len(result.preserved)}",
    ])
    if args.json:
        _emit(result.to_record())
        return EXIT_OK if result.diagnosis.healthy or result.dry_run else EXIT_FAILED
    print(text)
    return EXIT_OK if result.diagnosis.healthy or result.dry_run else EXIT_FAILED


def _cmd_uninstall(args: argparse.Namespace) -> int:
    from .lifecycle import uninstaller

    project = _project(args)
    interactive = False
    if args.purge and not args.yes and not args.dry_run and sys.stdin.isatty():
        preview = uninstaller.uninstall(project, purge=True, dry_run=True)
        print("The following paths will be permanently deleted:")
        for path in sorted(preview.removed):
            print(f"  {path}")
        interactive = input("Delete them? [y/N]: ").strip().lower() in ("y", "yes")
        if not interactive:
            print("Aborted. Nothing was removed.")
            return EXIT_OK

    result = uninstaller.uninstall(project, purge=args.purge, dry_run=args.dry_run,
                                   assume_yes=args.yes, interactive=interactive,
                                   force_unlock=args.force_unlock)
    return _report(args, result.to_record(), _uninstall_text(result))


def _cmd_update(args: argparse.Namespace) -> int:
    from .lifecycle import updater

    project = _project(args)
    if args.update_command == "check":
        outcome = updater.check(project, force=args.force)
        if args.json:
            _emit(outcome.to_record())
        else:
            print(outcome.message())
        return EXIT_OK
    if args.update_command == "rollback":
        record = updater.rollback(project, dry_run=args.dry_run)
        return _report(args, record,
                       f"rolled back to {record.get('to_version')} "
                       f"({len(record.get('restored', record.get('would_restore', [])))} files)"
                       + f"\nscope: {record.get('scope', '')}")

    result = updater.apply(project, dry_run=args.dry_run, force=args.force)
    text = (f"{'(dry-run) ' if result.dry_run else ''}"
            f"{result.from_version} -> {result.to_version or result.from_version}: "
            f"{'applied' if result.applied else 'nothing to do'}")
    if result.conflicts:
        text += ("\nYour edits were kept; the new versions are beside them as .new:\n  "
                 + "\n  ".join(sorted(result.conflicts)))
    return _report(args, result.to_record(), text)


LIFECYCLE_COMMANDS = {
    "init": _cmd_init,
    "profile": _cmd_profile,
    "status": _cmd_status,
    "doctor": _cmd_doctor,
    "repair": _cmd_repair,
    "uninstall": _cmd_uninstall,
    "update": _cmd_update,
}


def _print_versions() -> int:
    from . import __version__
    from .lifecycle import source as sourcelib, state as statelib

    payload = {"lifecycle": __version__, "state_schema": statelib.SCHEMA_VERSION}
    try:
        payload["stack"] = sourcelib.resolve().version
    except LifecycleError:
        payload["stack"] = "unknown (no distribution source)"
    try:
        from ainative_workplane import __version__ as runtime
        payload["workplane_runtime"] = runtime
    except ImportError:
        payload["workplane_runtime"] = "not installed"
    for key, value in payload.items():
        print(f"{key}: {value}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    # Verified commands are handed over verbatim, before argparse sees them: the
    # Work Plane owns its own grammar, its own output and its own exit codes.
    if arguments and arguments[0] in VERIFIED_COMMANDS:
        from ainative_workplane.cli import main as workplane_main

        return workplane_main(arguments)

    parser = build_parser()
    args = parser.parse_args(arguments)
    if getattr(args, "version", False):
        return _print_versions()
    if not args.command:
        parser.print_help()
        return EXIT_INVALID_REQUEST

    handler = LIFECYCLE_COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_INVALID_REQUEST
    try:
        return handler(args)
    except LifecycleError as refusal:
        if getattr(args, "json", False):
            _emit(refusal.to_record())
        else:
            print(f"refused: {refusal}", file=sys.stderr)
            for key, value in refusal.detail.items():
                print(f"  {key}: {value}", file=sys.stderr)
        return refusal.exit_code
    except KeyboardInterrupt:
        print("\ninterrupted — run `ainative doctor` to check for a partial operation",
              file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
