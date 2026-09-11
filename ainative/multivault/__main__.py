"""Multi-Vault CLI: audit query, doctor and context.

Doctor and context read only the Operator Authority Store and the repository
state; every check is fail-closed (UNKNOWN never renders as PASS) and the
context display never claims support without probe evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

from .audit import AuditLog
from .authority_store import AuthorityStore, AuthorityStoreCorruptError
from .binding import ALLOW_ROOT_FRESH, root_freshness
from .identity import measure_root_identity
from .status import ContextReport, doctor_report


def _doctor_checks(store_path: Path, domain: str, repository: Path, vault_root: Path | None = None) -> dict:
    checks: dict = {"canary": None}
    try:
        binding = AuthorityStore(store_path).binding(domain)
        checks["binding"] = binding is not None
    except (AuthorityStoreCorruptError, OSError):
        binding = None
        checks["binding"] = None
    if vault_root is None:
        checks["root_freshness"] = None
    else:
        measured = measure_root_identity(str((binding or {}).get("vault", "")), vault_root)
        verdict = root_freshness(binding, measured)
        checks["root_freshness"] = verdict.decision == ALLOW_ROOT_FRESH
    try:
        inside = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        checks["repository"] = inside.returncode == 0 and inside.stdout.strip() == "true"
        hooks = subprocess.run(
            ["git", "-C", str(repository), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            check=False,
        )
        checks["managed_hooks_path"] = bool(hooks.stdout.strip()) if hooks.returncode == 0 else False
    except OSError:
        checks["repository"] = None
        checks["managed_hooks_path"] = None
    return checks


def _context_report(store_path: Path, domain: str, harness: str, provider_class: str, model: str, routing: str) -> ContextReport | None:
    try:
        binding = AuthorityStore(store_path).binding(domain)
    except (AuthorityStoreCorruptError, OSError):
        return None
    if not binding:
        return None
    return ContextReport(
        security_domain_id=domain,
        classification=str(binding.get("classification", "PERSONAL")),
        vault_identity=str(binding.get("vault", "")),
        checkout_identity=str(binding.get("checkout", "")),
        harness=harness,
        provider_class=provider_class,
        model=model,
        routing=routing,
        qualification="UNKNOWN",
        observation_windows=(),
        unsupported_capabilities=("probe_evidence",),
        supported=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ainative.multivault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query = subparsers.add_parser("audit-query", help="print audit records as JSON lines")
    query.add_argument("log", type=Path)
    query.add_argument("--domain")
    query.add_argument("--decision")
    query.add_argument("--reason-code")

    doctor = subparsers.add_parser("doctor", help="fail-closed readiness checks")
    doctor.add_argument("--store", type=Path, required=True)
    doctor.add_argument("--domain", required=True)
    doctor.add_argument("--repo", type=Path, default=Path("."))
    doctor.add_argument("--vault-root", type=Path, default=None)

    context = subparsers.add_parser("context", help="describe the resolved security context")
    context.add_argument("--store", type=Path, required=True)
    context.add_argument("--domain", required=True)
    context.add_argument("--harness", default="UNKNOWN")
    context.add_argument("--provider-class", default="UNKNOWN")
    context.add_argument("--model", default="UNKNOWN")
    context.add_argument("--routing", default="UNKNOWN")

    args = parser.parse_args(argv)

    if args.command == "audit-query":
        for record in AuditLog(args.log).query(
            security_domain_id=args.domain,
            decision=args.decision,
            reason_code=args.reason_code,
        ):
            print(json.dumps(asdict(record), sort_keys=True))
        return 0

    if args.command == "doctor":
        report = doctor_report(_doctor_checks(args.store, args.domain, args.repo, args.vault_root))
        for name, verdict in report:
            print(f"{verdict}\t{name}")
        return 0 if all(verdict == "PASS" for _name, verdict in report) else 1

    if args.command == "context":
        report = _context_report(args.store, args.domain, args.harness, args.provider_class, args.model, args.routing)
        if report is None:
            print("binding: MISSING")
            return 1
        print(report.render())
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())