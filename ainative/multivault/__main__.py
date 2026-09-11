"""Minimal Multi-Vault CLI: audit query.

Doctor/context wiring over the operator store arrives with the runtime CLI;
this entry point is real and read-only today.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .audit import AuditLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ainative.multivault")
    subparsers = parser.add_subparsers(dest="command", required=True)
    query = subparsers.add_parser("audit-query", help="print audit records as JSON lines")
    query.add_argument("log", type=Path)
    query.add_argument("--domain")
    query.add_argument("--decision")
    query.add_argument("--reason-code")
    args = parser.parse_args(argv)
    if args.command == "audit-query":
        for record in AuditLog(args.log).query(
            security_domain_id=args.domain,
            decision=args.decision,
            reason_code=args.reason_code,
        ):
            print(json.dumps(asdict(record), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())