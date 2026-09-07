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

    knowledge = commands.add_parser(
        "knowledge", help="Capture, review and track knowledge candidates.")
    knowledge_commands = knowledge.add_subparsers(dest="knowledge_command", required=True)

    knowledge_status = knowledge_commands.add_parser(
        "status", help="Store health and candidate counts.")
    _add_common(knowledge_status, dry_run=False)

    capture = knowledge_commands.add_parser(
        "capture", help="Record one knowledge candidate.")
    capture.add_argument("--kind", required=True,
                         help="candidate class (e.g. PROJECT_RULE, FAILURE_PATTERN)")
    capture.add_argument("--claim", required=True, help="the proposed durable fact")
    capture.add_argument("--agent", default="unknown", help="originating harness")
    capture.add_argument("--session", default=None, help="originating session id")
    capture.add_argument("--origin", default="manual",
                         help="origin type (e.g. user_correction, manual)")
    capture.add_argument("--module", default=None, help="owning module, if any")
    capture.add_argument("--path", dest="paths", action="append", default=[],
                         help="source path the claim was observed in (repeatable)")
    _add_common(capture)

    candidates = knowledge_commands.add_parser(
        "candidates", help="List stored candidates.")
    candidates.add_argument("--status", default=None, help="filter by state")
    candidates.add_argument("--kind", default=None, help="filter by class")
    _add_common(candidates, dry_run=False)

    inspect = knowledge_commands.add_parser("inspect", help="Show one candidate.")
    inspect.add_argument("candidate_id", help="kc_... identifier")
    _add_common(inspect, dry_run=False)

    transition = knowledge_commands.add_parser(
        "transition", help="Move a candidate to a new state.")
    transition.add_argument("candidate_id", help="kc_... identifier")
    transition.add_argument("to_status", help="target state")
    transition.add_argument("--actor", default="cli", help="who decides")
    _add_common(transition)

    classify = knowledge_commands.add_parser(
        "classify", help="Set the kind and move PENDING to CLASSIFIED.")
    classify.add_argument("candidate_id", help="kc_... identifier")
    classify.add_argument("--kind", default=None, help="override the kind")
    classify.add_argument("--actor", default="cli", help="who decides")
    _add_common(classify)

    evidence = knowledge_commands.add_parser(
        "evidence", help="Append one evidence item to a candidate.")
    evidence.add_argument("candidate_id", help="kc_... identifier")
    evidence.add_argument("--type", required=True, help="evidence type")
    evidence.add_argument("--locator", default="", help="where it was observed")
    evidence.add_argument("--digest", default=None, help="content digest")
    evidence.add_argument("--actor", default="cli", help="who observed")
    _add_common(evidence)

    verify = knowledge_commands.add_parser(
        "verify", help="Replay dedupe, conflict and evidence checks.")
    verify.add_argument("candidate_id", help="kc_... identifier")
    verify.add_argument("--actor", default="cli", help="who reviews")
    _add_common(verify)

    promote = knowledge_commands.add_parser(
        "promote", help="Apply an approved canonical patch.")
    promote.add_argument("candidate_id", help="kc_... identifier")
    promote.add_argument("--operation", required=True,
                         help="ADD, MERGE, REFINE or SUPERSEDE")
    promote.add_argument("--approve", default=None,
                         help="human approval statement (required)")
    promote.add_argument("--expect-base", dest="expect_base", default=None,
                         help="base digest from the --dry-run preview (required)")
    promote.add_argument("--target", default=None, help="explicit target file")
    promote.add_argument("--anchor", default=None, help="anchor text for edits")
    promote.add_argument("--actor", default="cli", help="who promotes")
    _add_common(promote)

    reject = knowledge_commands.add_parser(
        "reject", help="Refuse a candidate (no canonical write).")
    reject.add_argument("candidate_id", help="kc_... identifier")
    reject.add_argument("--actor", default="cli", help="who decides")
    _add_common(reject)

    reconcile_cmd = knowledge_commands.add_parser(
        "reconcile", help="Heal a crashed promotion.")
    reconcile_cmd.add_argument("candidate_id", help="kc_... identifier")
    _add_common(reconcile_cmd)

    retrieve = knowledge_commands.add_parser(
        "retrieve", help="Assemble a bounded deterministic context bundle.")
    retrieve.add_argument("--focus", action="append", default=[],
                          help="project-relative path to center on (repeatable)")
    retrieve.add_argument("--task-type", dest="task_type", default="general")
    retrieve.add_argument("--adr", action="append", default=[],
                          help="ADR ref to include (repeatable)")
    retrieve.add_argument("--recall", default=None,
                          help="semantic recall query (needs a provider, K5b)")
    retrieve.add_argument("--max-items", dest="max_items", type=int, default=20)
    retrieve.add_argument("--max-bytes", dest="max_bytes", type=int, default=65536)
    retrieve.add_argument("--max-excerpt", dest="max_excerpt", type=int, default=2000)
    retrieve.add_argument("--max-candidates", dest="max_candidates", type=int,
                          default=5)
    _add_common(retrieve, dry_run=False)

    context = commands.add_parser(
        "context", help="Working memory: save, checkpoint and restore operational state.")
    context_commands = context.add_subparsers(dest="context_command", required=True)

    context_status = context_commands.add_parser(
        "status", help="Working state and checkpoint counts.")
    _add_common(context_status, dry_run=False)

    save = context_commands.add_parser("save", help="Create or merge working state.")
    save.add_argument("--task", default=None, help="active task")
    save.add_argument("--goal", default=None, help="session goal")
    save.add_argument("--plan", default=None, help="current plan")
    save.add_argument("--result", default=None, help="latest test results")
    save.add_argument("--next-action", dest="next_action", default=None)
    save.add_argument("--touch", dest="touches", action="append", default=[])
    save.add_argument("--hypothesis", dest="hypotheses", action="append", default=[])
    save.add_argument("--finding", dest="findings", action="append", default=[])
    save.add_argument("--question", dest="questions", action="append", default=[])
    save.add_argument("--test", dest="tests", action="append", default=[])
    save.add_argument("--blocker", dest="blockers", action="append", default=[])
    save.add_argument("--candidate", dest="candidates", action="append", default=[])
    save.add_argument("--ttl", type=int, default=None,
                      help="seconds until this state expires")
    _add_common(save)

    make_checkpoint = context_commands.add_parser(
        "checkpoint", help="Freeze state for compaction.")
    make_checkpoint.add_argument("--reason", default="manual")
    _add_common(make_checkpoint)

    restore = context_commands.add_parser("restore", help="Bring back a checkpoint.")
    restore.add_argument("checkpoint_id")
    _add_common(restore)

    clear = context_commands.add_parser("clear", help="Discard transient state.")
    _add_common(clear, yes=True)

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


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .lifecycle import recovery
    from ainative.knowledge import health as knowledge_health

    diagnosis = recovery.diagnose(_project(args), check_updates=args.check_updates)
    # Knowledge health is informational: the lifecycle is usable without any
    # knowledge store (backward compatibility), so a missing or corrupt store
    # is reported, never fatal to this command. K9 will decide whether a
    # corrupt store should fail the exit code.
    knowledge = knowledge_health.build(_project(args))
    if args.json:
        record = diagnosis.to_record()
        record["knowledge"] = knowledge.to_record()
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
        print(f"  {knowledge.render()}")
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


def _knowledge_refuse(args: argparse.Namespace, error) -> int:
    if getattr(args, "json", False):
        _emit(error.to_record())
    else:
        print(f"refused: {error}", file=sys.stderr)
        for key, value in error.detail.items():
            print(f"  {key}: {value}", file=sys.stderr)
    return error.exit_code


def _knowledge_capture_fields(args: argparse.Namespace, project) -> dict:
    from ainative.lifecycle import state as statelib

    return {
        "project": str(project),
        "agent": args.agent,
        "session": args.session or statelib.new_identifier("sess"),
        "origin_type": args.origin,
        "kind": args.kind.upper(),
        "claim": args.claim,
        "module": args.module,
        "source_paths": tuple(args.paths or ()),
        "repository": project,
    }


def _knowledge_status(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import health as healthlib

    report = healthlib.build(project)
    return _report(args, report.to_record(), report.render())


def _knowledge_candidates(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import store as storelib

    wanted_status = args.status.upper() if args.status else None
    wanted_kind = args.kind.upper() if args.kind else None
    records = storelib.list_candidates(project, status=wanted_status, kind=wanted_kind)
    lines = [f"{item['candidate_id']}  {item['status']:<18} "
             f"{item['kind']:<20} {item['claim'][:80]}" for item in records]
    return _report(args, {"candidates": records}, "\n".join(lines) or "no candidates")


def _knowledge_inspect(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import store as storelib

    record = storelib.inspect_candidate(project, args.candidate_id)
    return _report(args, record, "\n".join([
        f"{record['candidate_id']}  {record['status']}  {record['kind']}",
        f"  claim: {record['claim']}",
        f"  target: {record['target_hint']}",
        f"  evidence: {len(record['evidence'])} item(s)",
    ]))


def _knowledge_capture(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import candidate as candidatelib
    from ainative.knowledge import store as storelib

    if args.dry_run:
        record = candidatelib.capture(**_knowledge_capture_fields(args, project))
        return _report(
            args, {"dry_run": True, "candidate": record},
            f"(dry-run \u2014 nothing was written)\n"
            f"{record['candidate_id']}  PENDING  {record['kind']}  "
            f"{record['target_hint']}")
    stored = storelib.append(project, candidatelib.capture(**_knowledge_capture_fields(args, project)))
    return _report(args, stored,
                   f"{stored['candidate_id']}  PENDING  {stored['kind']}  "
                   f"{stored['target_hint']}")


def _knowledge_transition(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import candidate as candidatelib
    from ainative.knowledge import store as storelib

    target = args.to_status.upper()
    if args.dry_run:
        current = storelib.inspect_candidate(project, args.candidate_id)
        updated = candidatelib.transition(current, target)
        return _report(
            args, {"dry_run": True, "candidate_id": updated["candidate_id"],
                   "from": current["status"], "to": updated["status"]},
            f"(dry-run \u2014 nothing was written)\n"
            f"{updated['candidate_id']}  {current['status']} -> {updated['status']}")
    updated = storelib.set_status(project, args.candidate_id, target, actor=args.actor)
    return _report(args, updated, f"{updated['candidate_id']}  {updated['status']}")


def _knowledge_classify(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import review as reviewlib

    if args.dry_run:
        from ainative.knowledge import store as storelib
        from ainative.knowledge.classifier import suggest

        current = storelib.inspect_candidate(project, args.candidate_id)
        chosen = current["kind"] if args.kind is None else args.kind.upper()
        suggestion = suggest(current["claim"], module=current["scope"].get("module"))
        return _report(args, {"dry_run": True, "candidate_id": current["candidate_id"],
                              "kind": chosen, "suggestion": suggestion},
                       f"(dry-run \u2014 nothing was written)\n"
                       f"{current['candidate_id']}  PENDING -> CLASSIFIED as {chosen} "
                       f"(suggested: {suggestion['kind']})")
    updated = reviewlib.classify_candidate(project, args.candidate_id,
                                           kind=args.kind, actor=args.actor)
    return _report(args, updated, f"{updated['candidate_id']}  CLASSIFIED as {updated['kind']}")


def _knowledge_evidence(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import evidence as evidencelib

    item = {"type": args.type.upper(), "locator": args.locator or "",
            "digest": args.digest}
    if args.dry_run:
        from ainative.knowledge.candidate import validate_evidence_item
        validated = validate_evidence_item(item)
        return _report(args, {"dry_run": True, "evidence": validated},
                       f"(dry-run \u2014 nothing was written)\n"
                       f"would append {validated['type']} {validated['locator'] or '-'}")
    stored, added = evidencelib.add_evidence(project, args.candidate_id, item,
                                             actor=args.actor)
    verb = "appended" if added else "already present"
    return _report(args, stored,
                   f"{stored['candidate_id']}  evidence {verb} "
                   f"({len(stored['evidence'])} item(s))")


def _render_verify(report: dict, prefix: str) -> str:
    lines = [f"{prefix}{report['candidate_id']}  {report['from']} -> {report['to']}",
             f"  evidence: {report['sufficiency_reason']}"]
    for finding in report["findings"]:
        lines.append(f"  {finding['class']} with {finding['with']}: {finding['explanation']}")
    return "\n".join(lines)


def _knowledge_verify(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import review as reviewlib

    if args.dry_run:
        preview = reviewlib.preview_verify(project, args.candidate_id)
        return _report(args, {"dry_run": True, **preview},
                       _render_verify(preview, "(dry-run \u2014 nothing was written)\n"))
    report = reviewlib.verify_candidate(project, args.candidate_id, actor=args.actor)
    return _report(args, report, _render_verify(report, ""))
def _knowledge_promote(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import policy as policylib
    from ainative.knowledge import promotion as promotionlib
    from ainative.knowledge import store as storelib
    from ainative.knowledge import targets as targetslib
    from ainative.knowledge.errors import KnowledgeError

    operation = args.operation.upper()
    if args.dry_run:
        candidate = storelib.inspect_candidate(project, args.candidate_id)
        dest = targetslib.resolve(project, candidate, target=args.target)
        target_class = policylib.classify_target(project, dest)
        plan = promotionlib.plan_promotion(project, args.candidate_id,
                                           operation=operation, actor=args.actor,
                                           target=args.target, anchor_text=args.anchor)
        lines = [f"(dry-run \u2014 nothing was written)",
                 f"{plan['candidate_id']}  {operation} -> {plan['target']} "
                 f"({target_class})",
                 f"  base: {plan['base_digest']}",
                 "  approval required: re-run with --approve \"<reason>\" "
                 f"--expect-base {plan['base_digest']}"]
        lines += [f"  {line}" for line in plan["diff_preview"]]
        preview = {key: plan[key] for key in
                   ("candidate_id", "operation", "target", "base_digest",
                    "result_digest", "actor", "anchor_text", "diff_preview")}
        return _report(args, {"dry_run": True, **preview,
                              "target_class": target_class}, "\n".join(lines))
    if not args.approve:
        candidate = storelib.inspect_candidate(project, args.candidate_id)
        dest = targetslib.resolve(project, candidate, target=args.target)
        policylib.check(project, candidate, dest, actor=args.actor, approve=None)
    if not args.expect_base:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "preview-first: run with --dry-run, then pass "
                             "--expect-base <base_digest>")
    candidate = storelib.inspect_candidate(project, args.candidate_id)
    dest = targetslib.resolve(project, candidate, target=args.target)
    approval = policylib.check(project, candidate, dest, actor=args.actor,
                               approve=args.approve)
    storelib.record_audit(project, candidate_id=args.candidate_id,
                          operation="APPROVE",
                          detail={**approval, "base_digest": args.expect_base},
                          actor=args.actor)
    outcome = promotionlib.apply_promotion(
        project, args.candidate_id, operation=operation, actor=args.actor,
        target=args.target, anchor_text=args.anchor, expect_base=args.expect_base)
    return _report(args, outcome,
                   f"{outcome['candidate_id']}  PROMOTED -> {outcome['target']}")


def _knowledge_reject(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import candidate as candidatelib
    from ainative.knowledge import store as storelib

    if args.dry_run:
        current = storelib.inspect_candidate(project, args.candidate_id)
        candidatelib.transition(current, "REJECTED")
        return _report(args, {"dry_run": True, "candidate_id": current["candidate_id"],
                              "from": current["status"], "to": "REJECTED"},
                       f"(dry-run \u2014 nothing was written)\n"
                       f"{current['candidate_id']}  {current['status']} -> REJECTED")
    updated = storelib.set_status(project, args.candidate_id, "REJECTED",
                                  actor=args.actor)
    return _report(args, updated, f"{updated['candidate_id']}  REJECTED")


def _knowledge_reconcile(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import promotion as promotionlib

    if args.dry_run:
        decision = promotionlib.describe_reconcile(project, args.candidate_id)
        return _report(args, {"dry_run": True, **decision},
                       f"(dry-run \u2014 nothing was written)\n"
                       f"{decision['candidate_id']}  {decision['state']}")
    outcome = promotionlib.reconcile(project, args.candidate_id)
    return _report(args, outcome, f"{outcome['candidate_id']}  {outcome['state']}")
def _knowledge_retrieve(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import retrieval as retrievallib

    budgets = retrievallib.Budgets(max_items=args.max_items,
                                   max_bytes=args.max_bytes,
                                   max_excerpt_chars=args.max_excerpt,
                                   max_candidates=args.max_candidates)
    bundle = retrievallib.assemble(project, focus=args.focus or ["."],
                                   task_type=args.task_type,
                                   adr_refs=args.adr or [],
                                   recall=args.recall, budgets=budgets)
    return _report(args, bundle.to_record(), bundle.render())
def _cmd_knowledge(args: argparse.Namespace) -> int:
    # Lazy imports live in the helpers above, like every other lifecycle
    # command: importing this module must never pull in more than the command
    # needs (ADR-0009 section 1), and knowledge must never touch
    # `ainative_workplane` (ADR-0011).
    from ainative.knowledge.errors import KnowledgeError

    handlers = {
        "status": _knowledge_status,
        "candidates": _knowledge_candidates,
        "inspect": _knowledge_inspect,
        "capture": _knowledge_capture,
        "transition": _knowledge_transition,
        "classify": _knowledge_classify,
        "evidence": _knowledge_evidence,
        "verify": _knowledge_verify,
        "promote": _knowledge_promote,
        "reject": _knowledge_reject,
        "reconcile": _knowledge_reconcile,
        "retrieve": _knowledge_retrieve,
    }
    try:
        return handlers[args.knowledge_command](args, _project(args))
    except KnowledgeError as refusal:
        return _knowledge_refuse(args, refusal)
    except KeyError:
        raise AssertionError(f"unknown knowledge command: {args.knowledge_command}")


def _context_merge_list(current: list, additions) -> list:
    merged = list(current)
    for item in additions or ():
        if item not in merged:
            merged.append(item)
    return merged


def _context_status(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import working as workinglib

    state, outcome = workinglib.load(project)
    checkpoints = workinglib.list_checkpoints(project)
    pending = workinglib.pending_candidate_ids(project)
    record = {"outcome": outcome,
              "working": state.to_record() if state is not None else None,
              "checkpoints": len(checkpoints),
              "pending_candidates": len(pending)}
    if state is None:
        text = "working: empty — nothing saved"
    elif outcome == workinglib.EXPIRED:
        text = f"working: EXPIRED — task: {state.task or '-'} | next: {state.next_action or '-'}"
    elif outcome == workinglib.RECOVERED:
        text = (f"working: RECOVERED from backup — task: {state.task or '-'} | "
                f"next: {state.next_action or '-'} (save to persist)")
    else:
        text = (f"working: current — task: {state.task or '-'} | "
                f"next: {state.next_action or '-'} | checkpoints: {len(checkpoints)} | "
                f"pending candidates: {len(pending)}")
    return _report(args, record, text)


def _context_save(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import working as workinglib

    current, _ = workinglib.load(project)
    state = current if current is not None else workinglib.WorkingState()
    if args.task is not None:
        state.task = args.task
    if args.goal is not None:
        state.goal = args.goal
    if args.plan is not None:
        state.plan = args.plan
    if args.result is not None:
        state.test_results = args.result
    if args.next_action is not None:
        state.next_action = args.next_action
    state.files_touched = _context_merge_list(state.files_touched, args.touches)
    state.current_hypotheses = _context_merge_list(state.current_hypotheses, args.hypotheses)
    state.confirmed_findings = _context_merge_list(state.confirmed_findings, args.findings)
    state.open_questions = _context_merge_list(state.open_questions, args.questions)
    state.tests_run = _context_merge_list(state.tests_run, args.tests)
    state.blockers = _context_merge_list(state.blockers, args.blockers)
    state.candidate_ids = _context_merge_list(state.candidate_ids, args.candidates)
    if args.ttl is not None:
        if args.ttl < 0:
            from ainative.knowledge.errors import KnowledgeError
            raise KnowledgeError("KNOWLEDGE_MALFORMED", "ttl must be >= 0")
        from datetime import datetime, timedelta, timezone
        state.expires_at = (datetime.now(timezone.utc)
                            + timedelta(seconds=args.ttl)).isoformat()
    if args.dry_run:
        validated = workinglib.WorkingState.from_record(state.to_record())
        return _report(args, {"dry_run": True, "working": validated.to_record()},
                       f"(dry-run \u2014 nothing was written)\n"
                       f"task: {validated.task or '-'} | next: {validated.next_action or '-'}")
    from ainative.knowledge.provenance import observe_repository
    state.repository_head = observe_repository(project).get("git_head")
    saved = workinglib.save(project, state)
    return _report(args, saved.to_record(),
                   f"working saved — task: {saved.task or '-'} | next: {saved.next_action or '-'}")


def _context_checkpoint(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import working as workinglib

    if args.dry_run:
        state, _ = workinglib.load(project)
        if state is None:
            from ainative.knowledge.errors import KnowledgeError
            raise KnowledgeError("KNOWLEDGE_NOT_FOUND", "nothing to checkpoint")
        pending = workinglib.pending_candidate_ids(project)
        return _report(args, {"dry_run": True, "pending_candidates": len(pending)},
                       f"(dry-run \u2014 nothing was written)\n"
                       f"would checkpoint task: {state.task or '-'} "
                       f"({len(pending)} pending candidate(s))")
    record = workinglib.checkpoint(project, reason=args.reason)
    return _report(args, record,
                   f"{record['checkpoint_id']}  {record['reason']}  "
                   f"{len(record['pending_candidate_ids'])} pending candidate(s)")


def _context_restore(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import working as workinglib

    if args.dry_run:
        record, status = workinglib.describe_restore(project, args.checkpoint_id)
    else:
        record, status = workinglib.restore(project, args.checkpoint_id)
    prefix = "(dry-run \u2014 nothing was written)\n" if args.dry_run else ""
    return _report(args, {"dry_run": bool(args.dry_run), "checkpoint_id": record["checkpoint_id"],
                          "status": status},
                   f"{prefix}{record['checkpoint_id']}  {status}")


def _context_clear(args: argparse.Namespace, project) -> int:
    from ainative.knowledge import working as workinglib
    from ainative.knowledge.errors import KnowledgeError

    if not args.yes and not args.dry_run:
        raise KnowledgeError("KNOWLEDGE_CONFIRMATION_REQUIRED",
                             "clear discards transient working state; "
                             "use --yes or --dry-run")
    if args.dry_run:
        existing = [path.name for path in
                    (workinglib.working_path(project), workinglib.backup_path(project))
                    if path.is_file()]
        existing += [f"checkpoints/{item['checkpoint_id']}.json"
                     for item in workinglib.list_checkpoints(project)]
        return _report(args, {"dry_run": True, "would_remove": sorted(existing)},
                       "(dry-run \u2014 nothing was written)\n" +
                       ("\n".join(f"  would remove {name}" for name in sorted(existing))
                        or "  nothing to remove"))
    removed = workinglib.clear(project)
    return _report(args, {"removed": removed},
                   "working cleared" if removed else "working already empty")


def _cmd_context(args: argparse.Namespace) -> int:
    from ainative.knowledge.errors import KnowledgeError

    handlers = {
        "status": _context_status,
        "save": _context_save,
        "checkpoint": _context_checkpoint,
        "restore": _context_restore,
        "clear": _context_clear,
    }
    try:
        return handlers[args.context_command](args, _project(args))
    except KnowledgeError as refusal:
        return _knowledge_refuse(args, refusal)
    except KeyError:
        raise AssertionError(f"unknown context command: {args.context_command}")
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
