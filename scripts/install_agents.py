#!/usr/bin/env python3
"""Install the shared AI-native stack into user-level agent directories.

Checkout frontend. The mechanics — managed blocks, links, rendered files and
the ownership manifest at `~/.ai-native/machine.json` — are owned by the
packaged `ainative.lifecycle.machine_install`, the same code path
`ainative machine init` runs. This script adds what only a checkout can do:

  * resolve and validate the v4 vault/slug pair through `vault_protocol.py`
    before a single harness file is touched.

Two distinct, separately-managed blocks are written into each supported
agent's instruction file:

  * "Shared engineering method" — the canonical rules from
    `<STACK>/AGENTS.md`, written to be the same on every machine.
  * "Vault governance" — a thin pointer to the project's v4 Obsidian
    vault (when configured), so every harness sees the same authority
    for project status, board, and contracts. The block contains NO
    contract text: it only references the vault and tells the agent
    where to find the contract.

The two blocks live inside their own BEGIN/END markers so a user-edited
block stays untouched and either block can be removed independently.
`--check` reports the block state for every harness (OK / MISSING /
STALE / DUPLICATE) without writing anything, and `--dry-run` reports
the same actions without committing them.

Usage:
    python3 scripts/install_agents.py [--dry-run] [--check] [--home PATH]
                                      [--vault PATH] [--project-slug SLUG]
                                      [--no-vault-block]
    python3 scripts/install_agents.py --uninstall [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# The mechanics live in the installed package: the CLI and this script must
# never be two implementations of the same ownership rules.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ainative.lifecycle import machine, machine_install  # noqa: E402

METHOD_BEGIN = machine.METHOD_BEGIN
METHOD_END = machine.METHOD_END
VAULT_BEGIN = machine.VAULT_BEGIN
VAULT_END = machine.VAULT_END
SLUG_RE = machine_install.SLUG_RE


def _import_protocol():
    """Lazy import: keep the module usable when the user only wants
    the original "method-only" behaviour and the new files are absent
    from a partial checkout.
    """
    try:
        import vault_protocol  # type: ignore
    except ImportError:
        return None
    return vault_protocol


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install method, skills, agents, hooks and v4 vault "
                    "governance for every detected AI CLI."
    )
    parser.add_argument("--home", type=Path, default=Path.home(), help="target home directory")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing")
    parser.add_argument("--check", action="store_true", help="verify an existing installation")
    parser.add_argument("--uninstall", action="store_true",
                        help="reverse the recorded machine installation "
                             "(~/.ai-native/machine.json). Removes only assets this "
                             "installer wrote and the user has not modified; user "
                             "files and edited managed files are preserved. "
                             "Combine with --dry-run to preview.")
    parser.add_argument("--vault", type=Path, default=None,
                        help="v4 Obsidian vault path (default: $OBSIDIAN_VAULT). "
                             "When given, every supported harness gets a Vault "
                             "governance block that points to the vault.")
    parser.add_argument("--project-slug", type=str, default=None,
                        help="v4 project slug (default: $OBSIDIAN_PROJECT_SLUG). "
                             "Validated against the v4 grammar before any block is written.")
    parser.add_argument("--no-vault-block", action="store_true",
                        help="skip the vault governance block even when --vault is set "
                             "(use for the v4 setup_check matrix in CI).")
    return parser.parse_args()

def resolve_vault_pair(args: argparse.Namespace) -> tuple[Path | None, str | None, str | None]:
    """Return (vault, slug, error) from --vault/--project-slug + env.

    Returning a single error string (instead of raising) keeps the caller
    in charge of how a configuration problem is reported. The string
    describes the smallest fix the user can apply.

    A user who has not configured a vault gets `(None, None, None)` —
    the method block is still installed; the vault governance block is
    simply skipped. An error is only returned when the user *asked*
    for a vault (via env or argument) but the configuration is broken.
    """
    if args.no_vault_block:
        return (None, None, None)
    env_vault = os.environ.get("OBSIDIAN_VAULT")
    env_slug = os.environ.get("OBSIDIAN_PROJECT_SLUG")
    if not args.vault and not env_vault and not env_slug and not args.project_slug:
        return (None, None, None)

    protocol = _import_protocol()
    if protocol is None:
        return (None, None, "vault requested but vault_protocol.py is missing from this checkout")

    vault_path = protocol.resolve_vault_path(args.vault)
    if vault_path is None:
        return (None, None, "no vault path from --vault, positional, or OBSIDIAN_VAULT")
    slug_value = protocol.resolve_project_slug(args.project_slug)
    status = protocol.discover(vault_path, slug_value, run_validation=True)
    if status.status != "ok":
        return (None, None, f"vault discovery failed ({status.status}): {status.detail}")
    return (status.vault, status.slug, None)


def machine_uninstall(args: argparse.Namespace) -> int:
    """Print the reversal plan or apply it, then report like every other mode."""

    try:
        record = machine.uninstall(args.home, dry_run=args.dry_run)
    except machine.MachineLifecycleError as refusal:
        print(f"ERROR: {refusal}", file=sys.stderr)
        return 2
    mode = "dry-run" if args.dry_run else "uninstall"
    print(f"Machine {mode}: {len(record['removed'])} removal(s), "
          f"{len(record['preserved'])} preserved, {len(record['missing'])} already absent.")
    for path in record["removed"]:
        print(f"  REMOVE     {path}")
    for path in record["preserved"]:
        print(f"  PRESERVE   {path}")
    if record.get("detail"):
        print(f"  note: {record['detail']}")
    if not record["removed"] and not record["preserved"] and record.get("detail") is None:
        print("  note: the manifest recorded no assets")
    if not args.dry_run:
        print("Restart running AI clients to reload their configuration.")
    return 0


def main() -> int:
    args = parse_args()
    if args.uninstall:
        if args.check:
            print("ERROR: --check and --uninstall are mutually exclusive.", file=sys.stderr)
            return 2
        return machine_uninstall(args)
    if args.check and args.dry_run:
        print("ERROR: --check and --dry-run are mutually exclusive.", file=sys.stderr)
        return 2
    if args.vault and args.project_slug and not SLUG_RE.match(args.project_slug):
        print(f"ERROR: --project-slug {args.project_slug!r} does not match v4 grammar",
              file=sys.stderr)
        return 2

    # Resolve and validate the complete vault/slug pair before touching any
    # user profile. A bad registry entry must never leave a partial install.
    vault, slug, vault_err = resolve_vault_pair(args)
    if vault_err:
        print(f"ERROR: {vault_err}", file=sys.stderr)
        return 2

    stack = Path(__file__).resolve().parent.parent
    try:
        report = machine_install.install(
            args.home, stack, vault=vault, slug=slug,
            remove_vault_block=args.no_vault_block,
            dry_run=args.dry_run, check=args.check,
        )
    except machine.MachineLifecycleError as refusal:
        print(f"ERROR: {refusal}", file=sys.stderr)
        return 2

    mode = "check" if args.check else "dry-run" if args.dry_run else "install"
    print(f"\nStack {mode} ({sys.platform}): {report.changes} change(s), "
          f"{report.errors} issue(s).")
    if report.manifest is not None:
        print(f"Machine manifest: {report.manifest} ({report.assets} asset(s))")
    if not args.check:
        print("Restart running AI clients so they reload global rules, skills and plugins.")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
