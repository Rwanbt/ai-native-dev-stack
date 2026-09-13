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
import os
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
    update_check.add_argument("--strict", action="store_true",
                              help="exit non-zero when the source could not be consulted "
                                   "(OFFLINE / CHECK_FAILED); for CI gates")
    _add_common(update_check, dry_run=False)
    update_rollback = update_commands.add_parser(
        "rollback", help="Restore the project assets the last update replaced.")
    _add_common(update_rollback)
    _add_common(update)
    update.add_argument("--force", action="store_true",
                        help="apply even when the check reports no newer release")

    machine = commands.add_parser(
        "machine", help="Machine-wide integration: init, status, doctor, repair, uninstall.")
    machine_commands = machine.add_subparsers(dest="machine_command", required=True)
    machine_init = machine_commands.add_parser(
        "init", help="Install the shared method for every detected AI harness, "
                     "recording ownership in ~/.ai-native/machine.json.")
    machine_init.add_argument("--home", type=Path, default=None,
                              help="target home directory (default: your home)")
    machine_init.add_argument("--dry-run", action="store_true",
                              help="print the change plan; touch nothing")
    machine_init.add_argument("--vault", type=Path, default=None,
                              help="v4 Obsidian vault path (default: $OBSIDIAN_VAULT)")
    machine_init.add_argument("--project-slug", default=None,
                              help="v4 project slug (default: $OBSIDIAN_PROJECT_SLUG)")
    machine_init.add_argument("--remove-vault-block", action="store_true",
                              help="remove the vault governance block where present")
    machine_init.add_argument("--json", action="store_true", help="machine-readable output")

    machine_status = machine_commands.add_parser(
        "status", help="What the machine manifest records, and each asset's state.")
    machine_status.add_argument("--home", type=Path, default=None)
    machine_status.add_argument("--json", action="store_true")

    machine_doctor = machine_commands.add_parser(
        "doctor", help="Verdict on the recorded machine integration. Changes nothing.")
    machine_doctor.add_argument("--home", type=Path, default=None)
    machine_doctor.add_argument("--json", action="store_true")

    machine_repair = machine_commands.add_parser(
        "repair", help="Re-create what the manifest proves this stack installed.")
    machine_repair.add_argument("--home", type=Path, default=None)
    machine_repair.add_argument("--dry-run", action="store_true")
    machine_repair.add_argument("--json", action="store_true")

    machine_uninstall = machine_commands.add_parser(
        "uninstall", help="Remove only the recorded integration; keep everything else.")
    machine_uninstall.add_argument("--home", type=Path, default=None)
    machine_uninstall.add_argument("--dry-run", action="store_true")
    machine_uninstall.add_argument("--json", action="store_true")

    setup = commands.add_parser(
        "setup", help="Guided first run: project profile, machine integration, doctor.")
    setup.add_argument("--profile", choices=("standard", "verified"), default=None,
                       help="choose without the interactive prompt")
    setup.add_argument("--project", type=Path, default=None,
                       help="project root (default: the current directory)")
    setup.add_argument("--home", type=Path, default=None,
                       help="home for the machine integration (default: your home)")
    setup.add_argument("--machine", action="store_true",
                       help="consent to the machine-wide install without a prompt")
    setup.add_argument("--vault", type=Path, default=None,
                       help="v4 Obsidian vault path (default: $OBSIDIAN_VAULT)")
    setup.add_argument("--project-slug", default=None,
                       help="v4 project slug (default: $OBSIDIAN_PROJECT_SLUG)")
    setup.add_argument("--dry-run", action="store_true")
    setup.add_argument("--json", action="store_true")
    setup.add_argument("--non-interactive", action="store_true",
                       help="never prompt; choices come from flags only")

    from ainative.knowledge.cli import add_context_parser, add_knowledge_parser
    add_knowledge_parser(commands)
    add_context_parser(commands)

    for name in VERIFIED_COMMANDS:
        commands.add_parser(name, add_help=False,
                            help=f"Verified Work Plane: `ainative {name} --help`.")
    return parser


# --- lifecycle commands ---------------------------------------------------


def _ask(prompt: str) -> str | None:
    """Read one answer, or None when nobody is there to give one.

    `isatty()` alone is not enough: a piped or redirected stdin can still report
    a terminal and then raise EOFError on the first read, which surfaced as a
    traceback and exit 1 instead of a clean refusal (EMP-LC-009).
    """

    if not sys.stdin.isatty():
        return None
    try:
        return input(prompt).strip()
    except (EOFError, OSError):
        return None


def _choose_profile(args: argparse.Namespace) -> str:
    if args.profile:
        return args.profile
    print(PROFILE_PROMPT)
    for _ in range(3):
        answer = _ask("Profile [1/2] (1): ")
        if answer is None:
            break
        answer = answer.lower() or "1"
        if answer in ("1", "standard"):
            return "standard"
        if answer in ("2", "verified"):
            return "verified"
        print("Enter 1 for Standard or 2 for Verified.")
    raise LifecycleError(
        "PROFILE_INVALID",
        "no profile given and no terminal to ask on. "
        "Use `ainative init --profile standard` or `--profile verified`.")


def _report(args: argparse.Namespace, record: dict, text: str) -> int:
    if getattr(args, "json", False):
        _emit(record)
    else:
        print(text)
    return EXIT_OK


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


def _action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action.lower())


def _plan_text(result) -> str:
    plan = result.plan
    header = "(dry-run — nothing was written)\n" if result.dry_run else ""
    counts = ", ".join(f"{_action_label(action)} {count}"
                       for action, count in sorted(plan.counts().items())) or "no changes"
    lines = [f"{header}{plan.operation}: {plan.from_profile or 'none'} -> "
             f"{plan.to_profile or 'none'}", f"  {counts}"]
    for change in plan.changes:
        if change.action in ("SKIP",) and not result.dry_run:
            continue
        lines.append(f"  {_action_label(change.action):<18} {change.path}"
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
    answer = _ask("Delete them? [y/N]: ")
    return (answer or "").lower() in ("y", "yes")


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


def _doctor_collect(project: Path, check_updates: bool):
    """One whole-stack diagnosis, shared by `doctor` and `setup`."""

    from .lifecycle import environment, recovery
    from .knowledge import doctor as knowledgedoctor

    diagnosis = recovery.diagnose(project, check_updates=check_updates)
    knowledge = knowledgedoctor.knowledge_status(project)
    checks = environment.environment_checks(
        project, installed=diagnosis.installed,
        verified=diagnosis.active_profile == "verified")
    healthy = (diagnosis.healthy
               and knowledge["status"] != knowledgedoctor.STATUS_FAIL
               and not environment.failing(checks))
    return diagnosis, knowledge, checks, healthy


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .lifecycle import environment, recovery, updater
    from .knowledge import doctor as knowledgedoctor

    project = _project(args)
    diagnosis, knowledge, checks, healthy = _doctor_collect(
        project, args.check_updates)
    if args.json:
        record = diagnosis.to_record()
        record["knowledge"] = knowledge
        record["environment"] = checks
        _emit(record)
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
        if diagnosis.update:
            # Reported even when it cannot be applied: knowing a release exists
            # and knowing this runtime cannot apply it are two different facts
            # (#131 / AUD-202).
            print("Updates")
            print(f"  {updater.notice_line(diagnosis.update)}")
        print("Knowledge:")
        print(f"  status: {knowledge['status']}   store: {knowledge['store']}")
        if knowledge["status"] != knowledgedoctor.STATUS_FAIL:
            print(f"  candidates: {knowledge['candidates']}   "
                  f"review backlog: {knowledge['review_backlog']}   "
                  f"conflicts: {knowledge['conflicts']}   stale: {knowledge['stale']}")
            print(f"  working: {knowledge['working']['checkpoints']} checkpoint(s), "
                  f"{knowledge['working']['expired']} expired")
            print(f"  providers: graph {knowledge['graph_provider']}, "
                  f"semantic {knowledge['semantic_provider']}")
            print(f"  Multi-Vault scope: {knowledge['multivault_scope']}   "
                  f"promotion: {knowledge['promotion_mode']}   "
                  f"trust: {knowledge['trust']}")
        else:
            print(f"  FAIL: {knowledge['detail']}")
        print("Environment")
        for check in checks:
            marker = environment.OK if check["status"] == environment.OK else check["status"]
            print(f"  {marker:<16} {check['name']}: {check['detail']}")
            if check["impact"] and check["status"] != environment.OK:
                print(f"  {'':<16} -> {check['impact']}")
    return EXIT_OK if healthy else EXIT_FAILED


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
        answer = _ask("Delete them? [y/N]: ")
        if answer is not None:
            interactive = answer.lower() in ("y", "yes")
            if not interactive:
                print("Aborted. Nothing was removed.")
                return EXIT_OK
        # answer is None: the terminal claimed to exist but gave nothing back.
        # Fall through, so the uninstaller refuses with CONFIRMATION_REQUIRED
        # rather than this command silently reporting success.

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
        if args.strict and outcome.status in (updater.OFFLINE, updater.CHECK_FAILED):
            # Exit 0 means "the answer is what it is", never "the source was
            # reachable"; a CI gate that needs the second statement asks for it.
            return EXIT_FAILED
        return EXIT_OK
    if args.update_command == "rollback":
        record = updater.rollback(project, dry_run=args.dry_run)
        if record.get("dry_run"):
            # A dry run that says "rolled back" is lying about the only thing
            # it is allowed to do: describe (#131).
            text = ("(dry-run — nothing was written)\n"
                    f"would roll back to {record.get('to_version')} "
                    f"({len(record.get('would_restore', []))} files to restore, "
                    f"{len(record.get('would_remove', []))} to remove)\n"
                    f"scope: {record.get('scope', '')}")
        else:
            text = (f"rolled back to {record.get('to_version')} "
                    f"({len(record.get('restored', []))} files)"
                    f"\nscope: {record.get('scope', '')}")
        return _report(args, record, text)

    result = updater.apply(project, dry_run=args.dry_run, force=args.force)
    text = (f"{'(dry-run) ' if result.dry_run else ''}"
            f"{result.from_version} -> {result.to_version or result.from_version}: "
            f"{'applied' if result.applied else 'nothing to do'}")
    if result.conflicts:
        text += ("\nYour edits were kept; the new versions are beside them as .new:\n  "
                 + "\n  ".join(sorted(result.conflicts)))
    return _report(args, result.to_record(), text)


def _cmd_knowledge(args: argparse.Namespace) -> int:
    from ainative.knowledge.cli import cmd_knowledge

    return cmd_knowledge(args)


def _cmd_context(args: argparse.Namespace) -> int:
    from ainative.knowledge.cli import cmd_context

    return cmd_context(args)


def _machine_home(args: argparse.Namespace) -> Path:
    home = getattr(args, "home", None)
    return Path(home).expanduser() if home else Path.home()


def _machine_status_text(report: dict) -> str:
    if not report.get("present"):
        return report.get("detail") or "no machine manifest"
    lines = [f"Machine integration: {report['manifest']}",
             f"  stack version: {report.get('stack_version')}   "
             f"schema: {report.get('schema_version')}",
             f"  assets: {len(report.get('assets', []))}"]
    for state, count in sorted(report.get("counts", {}).items()):
        lines.append(f"  {state}: {count}")
    for asset in report.get("assets", []):
        if asset["state"] != "OK":
            detail = f"  {asset.get('detail', '')}".rstrip()
            lines.append(f"  {asset['state']:<10} {asset['path']}{detail}")
    lines.append("  healthy" if report.get("healthy")
                 else "  needs attention (`ainative machine repair`, then `machine doctor`)")
    return "\n".join(lines)


def _machine_vault_pair(args: argparse.Namespace) -> tuple[Path | None, str | None]:
    from .lifecycle import machine_install

    raw_vault = getattr(args, "vault", None) or os.environ.get("OBSIDIAN_VAULT")
    slug = getattr(args, "project_slug", None) or os.environ.get("OBSIDIAN_PROJECT_SLUG")
    vault = Path(raw_vault).expanduser() if raw_vault else None
    if (vault is None) != (slug is None):
        raise LifecycleError(
            "MACHINE_VAULT_PAIR_REQUIRED",
            "--vault and --project-slug must be given together (or both "
            "configured through OBSIDIAN_VAULT and OBSIDIAN_PROJECT_SLUG)")
    if slug is not None and not machine_install.SLUG_RE.match(slug):
        raise LifecycleError("MACHINE_SLUG_INVALID",
                             f"{slug!r} does not match the v4 slug grammar")
    if vault is not None and not (vault / "AGENTS.md").is_file():
        raise LifecycleError("MACHINE_VAULT_UNREADABLE",
                             f"{vault} does not look like a vault (no AGENTS.md); "
                             "nothing was written")
    return vault, slug


def _machine_init(args: argparse.Namespace, home: Path) -> int:
    from .lifecycle import machine_install
    from .lifecycle import source as sourcelib

    from .lifecycle import machine as machinelib

    stack = sourcelib.resolve().root
    vault, slug = _machine_vault_pair(args)
    try:
        report = machine_install.install(
            home, stack, vault=vault, slug=slug,
            remove_vault_block=args.remove_vault_block,
            dry_run=args.dry_run,
            printer=(lambda *_a, **_k: None) if args.json else print)
    except machinelib.MachineLifecycleError as refusal:
        raise LifecycleError(
            "MACHINE_MANIFEST_UNREADABLE",
            f"{refusal} — remove the manifest to start fresh, or inspect it "
            "with `ainative machine status`") from refusal
    if args.json:
        _emit({"operation": "machine init", "home": str(home),
               "stack_root": report.stack_root, "changes": report.changes,
               "errors": report.errors, "assets": report.assets,
               "dry_run": report.dry_run, "recorded": report.recorded,
               "manifest": str(report.manifest) if report.manifest else None})
    else:
        verb = "would be recorded" if report.dry_run else "recorded"
        mode = "(dry-run) " if report.dry_run else ""
        print(f"{mode}machine init: {report.changes} change(s), "
              f"{report.errors} issue(s), {report.assets} asset(s) {verb}")
        if report.manifest:
            print(f"manifest: {report.manifest}")
    return EXIT_OK if report.errors == 0 else EXIT_FAILED


def _machine_status(args: argparse.Namespace, home: Path, command: str) -> int:
    from .lifecycle import machine as machinelib
    from .lifecycle import machine_health

    try:
        report = machine_health.status(home)
    except machinelib.MachineLifecycleError as refusal:
        if args.json:
            _emit({"operation": f"machine {command}", "ok": False,
                   "error": str(refusal)})
        else:
            print(f"refused: {refusal}", file=sys.stderr)
        return EXIT_INVALID_REQUEST
    if args.json:
        _emit({"operation": f"machine {command}", **report})
    else:
        print(_machine_status_text(report))
    if command == "status":
        return EXIT_OK
    return EXIT_OK if report["healthy"] else EXIT_FAILED


def _machine_repair(args: argparse.Namespace, home: Path) -> int:
    from .lifecycle import machine as machinelib
    from .lifecycle import machine_health

    try:
        record = machine_health.repair(home, dry_run=args.dry_run)
    except machinelib.MachineLifecycleError as refusal:
        if args.json:
            _emit({"operation": "machine repair", "ok": False,
                   "error": str(refusal)})
        else:
            print(f"refused: {refusal}", file=sys.stderr)
        return EXIT_INVALID_REQUEST
    if args.json:
        _emit({"operation": "machine repair", **record})
    else:
        print("(dry-run — nothing was written)" if record["dry_run"]
              else "repair complete")
        print(f"  repaired:     {len(record['repaired'])}")
        print(f"  unrepairable: {len(record['unrepairable'])}")
        print(f"  preserved:    {len(record['preserved'])}")
        for item in record["unrepairable"]:
            print(f"  UNREPAIRABLE  {item['path']}  {item['detail']}")
        for item in record["preserved"]:
            print(f"  PRESERVED     {item['path']}  ({item['state']})")
    return EXIT_FAILED if record["unrepairable"] else EXIT_OK


def _machine_uninstall(args: argparse.Namespace, home: Path) -> int:
    from .lifecycle import machine as machinelib

    try:
        record = machinelib.uninstall(home, dry_run=args.dry_run)
    except machinelib.MachineLifecycleError as refusal:
        if args.json:
            _emit({"operation": "machine uninstall", "ok": False,
                   "error": str(refusal)})
        else:
            print(f"refused: {refusal}", file=sys.stderr)
        return EXIT_INVALID_REQUEST
    if args.json:
        _emit(record)
    else:
        mode = "(dry-run — nothing was written) " if record["dry_run"] else ""
        print(f"{mode}Machine uninstall: {len(record['removed'])} removal(s), "
              f"{len(record['preserved'])} preserved, "
              f"{len(record['missing'])} already absent.")
        for path in record["removed"]:
            print(f"  REMOVE     {path}")
        for path in record["preserved"]:
            print(f"  PRESERVE   {path}")
        if record.get("detail"):
            print(f"  note: {record['detail']}")
    return EXIT_OK


def _cmd_machine(args: argparse.Namespace) -> int:
    home = _machine_home(args)
    command = args.machine_command
    if command == "init":
        return _machine_init(args, home)
    if command in ("status", "doctor"):
        return _machine_status(args, home, command)
    if command == "repair":
        return _machine_repair(args, home)
    return _machine_uninstall(args, home)


def _cmd_setup(args: argparse.Namespace) -> int:
    from .lifecycle import setup_wizard

    return setup_wizard.run(args)


LIFECYCLE_COMMANDS = {
    "init": _cmd_init,
    "knowledge": _cmd_knowledge,
    "context": _cmd_context,
    "profile": _cmd_profile,
    "status": _cmd_status,
    "doctor": _cmd_doctor,
    "repair": _cmd_repair,
    "uninstall": _cmd_uninstall,
    "update": _cmd_update,
    "machine": _cmd_machine,
    "setup": _cmd_setup,
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
    # The Multi-Vault space owns its own grammar and exit codes as well; a thin
    # facade over the existing owners, never a second security implementation.
    if arguments and arguments[0] == "multivault":
        from ainative.multivault.__main__ import main as multivault_main

        return multivault_main(arguments[1:])

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
