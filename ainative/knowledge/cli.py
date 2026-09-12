"""Knowledge CLI: status, learn/capture, candidates, inspect, reject.

Only B1-merged primitives are used; the only state write exposed is
rejection through the deterministic machine (audited). No promotion,
no planner, no arbitrary transitions. All imports are function-local
so `ainative --help` never loads the knowledge layer unasked.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def add_knowledge_parser(commands) -> None:
    """Register `ainative knowledge ...` on the shared subparsers."""

    from ainative.cli import _add_common

    knowledge = commands.add_parser("knowledge", help="Durable knowledge control.")
    sub = knowledge.add_subparsers(dest="knowledge_command", required=True)

    status = sub.add_parser("status", help="Control storage health.")
    _add_common(status, dry_run=False)

    learn = sub.add_parser("learn", aliases=["capture"],
                           help="Capture one candidate as PENDING.")
    learn.add_argument("--claim", required=True, help="prose claim text")
    learn.add_argument("--kind", required=True, help="candidate kind, kebab")
    learn.add_argument("--identity-key", required=True,
                       help="root-specific identity key")
    learn.add_argument("--module", action="append", default=[],
                       help="known module id (repeatable)")
    learn.add_argument("--project-slug", default=None,
                       help="project slug (default: project directory name)")
    learn.add_argument("--shared-root", action="append", default=[],
                       help="configured shared root id (repeatable)")
    learn.add_argument("--assert-type", default=None,
                       choices=("integer", "string", "boolean", "enum"),
                       help="structured value type (default: string of claim)")
    learn.add_argument("--assert-value", default=None,
                       help="structured value (default: the claim text)")
    learn.add_argument("--actor", default="cli", help="capturing actor")
    _add_common(learn)

    candidates = sub.add_parser("candidates", help="List stored candidates.")
    candidates.add_argument("--status", default=None, help="filter by state")
    candidates.add_argument("--limit", type=int, default=50)
    _add_common(candidates, dry_run=False)

    inspect = sub.add_parser("inspect", help="Show one candidate.")
    inspect.add_argument("candidate_id", help="candidate identifier")
    _add_common(inspect, dry_run=False)

    reject = sub.add_parser("reject", help="Move one candidate to REJECTED.")
    reject.add_argument("candidate_id", help="candidate identifier")
    reject.add_argument("--actor", default="cli", help="rejecting actor")
    reject.add_argument("--reason", default="", help="rejection reason")
    _add_common(reject)


    import_parser = sub.add_parser("import", help="Stage foreign harness learnings as candidates.")
    import_parser.add_argument("source", help="path to a memory export (.md bullets or .json array)")
    import_parser.add_argument("--harness", required=True)
    import_parser.add_argument("--format", choices=("auto", "md", "json"), default="auto")
    import_parser.add_argument("--apply", action="store_true",
                               help="stage candidates; without it this is a preview (zero writes)")
    import_parser.add_argument("--project-slug", default=None)
    import_parser.add_argument("--module", action="append", default=[])
    import_parser.add_argument("--shared-root", action="append", default=[])
    import_parser.add_argument("--actor", default="operator")
    import_parser.add_argument("--origin-project", default=None)
    import_parser.add_argument("--origin-repository", default=None)
    import_parser.add_argument("--origin-session", default=None)


    maintain = sub.add_parser("maintain", help="Advisory maintenance; dry-run unless --apply-safe.")
    maintain.add_argument("--apply-safe", action="store_true",
                          help="remove only provably expired working checkpoints")

    export = sub.add_parser("export", help="Export the JSONL stores to a portable bundle.")
    export.add_argument("--out", required=True)

    reset_derived = sub.add_parser("reset-derived", help="Remove registered derived paths (registry is empty by design).")
    reset_derived.add_argument("--apply-safe", action="store_true")

    stale = sub.add_parser("stale", help="Evaluate dependency staleness of candidates (read-only).")

    consolidate = sub.add_parser("consolidate", help="Advisory consolidation pass (reads only).")

    review = sub.add_parser("review", help="Advisory review queue (read-only).")
    conflicts = sub.add_parser("conflicts", help="Conflict/advisory entries only (read-only).")

def _project(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "project", None) or Path.cwd())


def _report(args: argparse.Namespace, record: dict, text: str) -> int:
    from ainative.cli import _emit, _report as _shared_report

    return _shared_report(args, record, text)


def _cmd_knowledge_status(args: argparse.Namespace) -> int:
    from ainative.knowledge import paths as controlpaths
    from ainative.knowledge import store as storelib

    project = _project(args)
    policy = controlpaths.ensure_policy(project)
    status = storelib.storage_status(project)
    record = {"policy": policy, "storage": status}
    lines = [f"candidates: {status['counts']['candidates']}",
             f"supports: {status['counts']['supports']}",
             f"audit events: {status['counts']['audit']}",
             f"total bytes: {status['total_bytes']}"]
    if policy.get("enforced"):
        lines.append("control path policy: enforced")
    else:
        lines.append(f"control path policy: {policy.get('reason')}")
    for warning in status["warnings"]:
        lines.append(f"warning: {warning}")
    return _report(args, record, "\n".join(lines))


def _coerce_value(kind: str | None, raw: str | None, claim: str) -> dict:
    from ainative.knowledge.assertions import normalize_value

    if raw is None:
        return {"type": "string", "value": claim}
    if kind in (None, "string", "enum"):
        return normalize_value({"type": kind or "string", "value": raw})
    if kind == "integer":
        try:
            return normalize_value(int(raw))
        except ValueError as error:
            from ainative.knowledge.errors import KnowledgeError
            raise KnowledgeError("KNOWLEDGE_MALFORMED",
                                 "assert value is not an integer") from error
    if kind == "boolean":
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes"):
            return normalize_value(True)
        if lowered in ("false", "0", "no"):
            return normalize_value(False)
        from ainative.knowledge.errors import KnowledgeError
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "assert value is not a boolean")
    return normalize_value({"type": "string", "value": raw})


def _cmd_knowledge_learn(args: argparse.Namespace) -> int:
    from ainative.knowledge import assertions as assertionslib
    from ainative.knowledge import classifier as classifierlib
    from ainative.knowledge import identity as identitylib
    from ainative.knowledge import states as stateslib
    from ainative.knowledge import store as storelib
    from ainative.knowledge.errors import KnowledgeError
    from ainative.lifecycle import state as statelib

    project = _project(args)
    slug = args.project_slug or project.resolve().name
    identity = identitylib.parse_identity(
        args.identity_key, modules=frozenset(args.module or ()),
        project_slug=slug, shared_roots=frozenset(args.shared_root or ()))
    attested = identitylib.attest(identity, actor=args.actor)
    value = _coerce_value(args.assert_type, args.assert_value, args.claim)
    hashed = assertionslib.assertion_hash(identity, identity.scope, value)
    stamp = statelib.now()
    record = {"schema_version": 1,
              "candidate_id": statelib.new_identifier("cand"),
              "kind": args.kind,
              "state": stateslib.PENDING,
              "created_at": stamp, "updated_at": stamp,
              "source": {"origin": "cli-manual"},
              "scope": {"project": slug},
              "claim": args.claim,
              "identity": {"identity_key": identity.key,
                           "identity_key_grammar_version":
                               identitylib.IDENTITY_GRAMMAR_VERSION},
              "assertion_hash": hashed["assertion_hash"],
              "assertion_normalization_version":
                  assertionslib.NORMALIZATION_VERSION,
              "hash_algorithm": assertionslib.HASH_ALGORITHM,
              "assertion_value": hashed["value"],
              "provenance": {"actor": args.actor, "origin": "cli",
                             "identity_confirmed_by": attested["confirmed_by"]}}
    suggestion = classifierlib.suggest(
        args.claim, module=(args.module[0] if args.module else None))
    note = f"; advisory kind suggestion: {suggestion['kind']}"
    if args.dry_run:
        from ainative.knowledge.bounds import Bounds
        stored = storelib.validate_candidate(record, bounds=Bounds())
        return _report(args, {"dry_run": True, "candidate": stored},
                       f"would capture {stored['candidate_id']} "
                       f"({stored['kind']}) as PENDING" + note)
    stored = storelib.append_candidate(project, record)
    return _report(args, {"candidate": stored},
                   f"captured {stored['candidate_id']} ({stored['kind']}) as PENDING" + note)


def _cmd_knowledge_candidates(args: argparse.Namespace) -> int:
    from ainative.knowledge import states as stateslib
    from ainative.knowledge import store as storelib
    from ainative.knowledge.errors import KnowledgeError

    if args.status is not None and args.status not in stateslib.STATES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "unknown state filter")
    records = storelib.list_candidates(_project(args))
    if args.status is not None:
        records = [item for item in records if item.get("state") == args.status]
    total = len(records)
    records = records[: max(0, args.limit)]
    lines = [f"{item.get('candidate_id')}  {item.get('state')}  "
             f"{item.get('kind')}  {str(item.get('claim'))[:60]}"
             for item in records] or ["no candidates"]
    return _report(args, {"candidates": records, "total": total},
                   "\n".join(lines))


def _cmd_knowledge_inspect(args: argparse.Namespace) -> int:
    from ainative.knowledge import store as storelib

    record = storelib.get_candidate(_project(args), args.candidate_id)
    supports = storelib.list_supports(_project(args), args.candidate_id)
    lines = [f"id: {record.get('candidate_id')}",
             f"kind: {record.get('kind')}",
             f"state: {record.get('state')}",
             f"identity: {record.get('identity', {}).get('identity_key')}",
             f"claim: {record.get('claim')}",
             f"supports: {len(supports)}"]
    return _report(args, {"candidate": record, "supports": supports},
                   "\n".join(lines))


def _cmd_knowledge_reject(args: argparse.Namespace) -> int:
    from ainative.knowledge import store as storelib

    if args.dry_run:
        record = storelib.get_candidate(_project(args), args.candidate_id)
        return _report(args, {"dry_run": True,
                              "candidate_id": record.get("candidate_id"),
                              "from": record.get("state"), "to": "REJECTED"},
                       f"would move {record.get('candidate_id')} "
                       f"from {record.get('state')} to REJECTED")
    updated = storelib.transition_state(_project(args), args.candidate_id,
                                        "REJECTED", actor=args.actor,
                                        reason=args.reason)
    return _report(args, {"candidate": updated},
                   f"rejected {updated.get('candidate_id')}")


_HANDLERS = {
    "status": _cmd_knowledge_status,
    "learn": _cmd_knowledge_learn,
    "capture": _cmd_knowledge_learn,
    "candidates": _cmd_knowledge_candidates,
    "inspect": _cmd_knowledge_inspect,
    "reject": _cmd_knowledge_reject,
}


def _cmd_knowledge_import(args: argparse.Namespace) -> int:
    from ainative.knowledge import imports as importslib
    from ainative.knowledge.errors import KnowledgeError

    project = _project(args)
    slug = args.project_slug or project.resolve().name
    source = Path(args.source)
    try:
        if args.apply:
            report = importslib.apply(
                project, source, harness=args.harness, project_slug=slug,
                modules=args.module, shared_roots=args.shared_root,
                actor=args.actor, origin_project=args.origin_project,
                origin_repository=args.origin_repository,
                origin_session=args.origin_session, format=args.format)
            return _report(args, report,
                           f"import: staged {len(report['created'])} candidate(s) "
                           f"from {report['harness']}; refused {len(report['refused'])}")
        report = importslib.preview(
            source, harness=args.harness, project_slug=slug,
            modules=args.module, shared_roots=args.shared_root,
            actor=args.actor, format=args.format)
        return _report(args, report,
                       f"import preview: {len(report['staged'])} item(s) resolvable, "
                       f"{len(report['refused'])} refused; no write performed")
    except KnowledgeError as error:
        return _report(args, {"error": error.code, "message": error.message},
                       f"import refused: {error.code}: {error.message}")


def _cmd_knowledge_maintain(args: argparse.Namespace) -> int:
    from ainative.knowledge import maintenance as maintenancelib

    report = maintenancelib.maintain(_project(args), apply_safe=args.apply_safe)
    return _report(args, report,
                   f"maintain: {report['action']}; "
                   f"expired={report['removable_expired_checkpoints']} "
                   f"kept={report['kept_checkpoints']}")


def _cmd_knowledge_export(args: argparse.Namespace) -> int:
    from ainative.knowledge import maintenance as maintenancelib

    report = maintenancelib.export(_project(args), Path(args.out))
    return _report(args, report,
                   f"export: {report['exported']} file(s) -> {report['target']}")


def _cmd_knowledge_reset_derived(args: argparse.Namespace) -> int:
    from ainative.knowledge import maintenance as maintenancelib

    report = maintenancelib.reset_derived(_project(args), apply_safe=args.apply_safe)
    return _report(args, report,
                   f"reset-derived: registered={len(report['registered'])} "
                   f"removed={len(report.get('removed', []))}")


def _cmd_knowledge_stale(args: argparse.Namespace) -> int:
    from ainative.knowledge import staleness as stalenesslib
    from ainative.knowledge import store as storelib

    project = _project(args)
    records = storelib.list_candidates(project)
    reports = []
    for record in records:
        dependencies = record.get("dependencies")
        if not dependencies:
            continue
        result = stalenesslib.evaluate(project, dependencies)
        decay = stalenesslib.decay_class(record)
        reports.append({"candidate_id": record.get("candidate_id"),
                        "signal": result["signal"],
                        "decay_class": decay,
                        "retrieval_penalty": stalenesslib.retrieval_penalty(result["signal"], decay),
                        "review_priority": stalenesslib.review_priority(result["signal"], decay),
                        "details": result["details"],
                        "refused": result["refused"]})
    lines = [f"{item['candidate_id']}  {item['signal']}  penalty={item['retrieval_penalty']} "
             f"review={item['review_priority']}" for item in reports] or [
        f"no candidates with dependency metadata (scanned {len(records)})"]
    return _report(args, {"reports": reports, "scanned": len(records)},
                   "\n".join(lines))


def _cmd_knowledge_consolidate(args: argparse.Namespace) -> int:
    from ainative.knowledge import consolidation as consolidationlib

    report = consolidationlib.consolidate(_project(args))
    lines = [f"{item['candidate_id']}  {item['outcome']}  ({item['verdict']})"
             for item in report["proposals"]] or [
        f"no reviewable candidates (scanned {report['scanned']})"]
    lines.append(report["note"])
    return _report(args, report, "\n".join(lines))


def _cmd_knowledge_review(args: argparse.Namespace) -> int:
    from ainative.knowledge import review as reviewlib

    report = reviewlib.review_queue(_project(args))
    lines = [f"p{item['review_priority']}  {item['candidate_id']}  {item['outcome']}  "
             f"({item['verdict']})" for item in report["queue"]] or [
        f"queue empty (scanned {report['scanned']})"]
    lines.append(f"promotion: {report['promotion']['eligibility']}; "
                 f"trust: {report['trust']['qualification']}")
    return _report(args, report, "\n".join(lines))


def _cmd_knowledge_conflicts(args: argparse.Namespace) -> int:
    from ainative.knowledge import review as reviewlib

    report = reviewlib.conflicts(_project(args))
    lines = [f"{item['candidate_id']}  {item['verdict']}  "
             f"holders={','.join(item.get('holders', [])) or '-'}"
             for item in report["conflicts"]] or [f"no conflicts (scanned {report['scanned']})"]
    return _report(args, report, "\n".join(lines))


_HANDLERS["import"] = _cmd_knowledge_import


_HANDLERS["review"] = _cmd_knowledge_review
_HANDLERS["conflicts"] = _cmd_knowledge_conflicts
_HANDLERS["consolidate"] = _cmd_knowledge_consolidate
_HANDLERS["stale"] = _cmd_knowledge_stale
_HANDLERS["maintain"] = _cmd_knowledge_maintain
_HANDLERS["export"] = _cmd_knowledge_export
_HANDLERS["reset-derived"] = _cmd_knowledge_reset_derived


def cmd_knowledge(args: argparse.Namespace) -> int:
    """Dispatch `ainative knowledge ...` (called lazily from the top CLI)."""

    from ainative.knowledge.errors import KnowledgeError
    from ainative.cli import _emit

    handler = _HANDLERS.get(getattr(args, "knowledge_command", None))
    if handler is None:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", "unknown knowledge command")
    try:
        return handler(args)
    except KnowledgeError as refusal:
        if getattr(args, "json", False):
            _emit(refusal.to_record())
        else:
            print(f"refused: {refusal}", file=sys.stderr)
        return refusal.exit_code


__all__ = ["add_knowledge_parser", "cmd_knowledge"]
