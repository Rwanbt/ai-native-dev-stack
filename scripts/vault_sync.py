#!/usr/bin/env python3
"""vault_sync.py — Sync an Obsidian vault with its private git remote.

Cross-platform: Linux, macOS, Windows. One implementation; the .ps1 and .sh
entry points are shims.

Replaces the previous PowerShell script, which:
  - pushed a hardcoded `master` instead of the current branch, so a vault
    sitting on any other branch was never pushed;
  - printed a success message without checking anything, so 13 days of notes
    looked backed up while they existed only on one machine;
  - always exited 0, so the once-daily wrapper recorded "synced today" even
    after a divergence that pushed nothing.

Guarantees here, in order of importance:
  1. Never reports success it has not verified — the push is confirmed by
     re-reading the remote ref afterwards.
  2. Never pushes to a branch other than the one checked out.
  3. Refuses to run on a non-primary branch: a vault has no reason to have
     branches, and a side branch is how the backup silently stopped working.
  4. Refuses to push content matching a known credential pattern.
  5. Stops on divergence instead of guessing; exits non-zero so the
     once-daily wrapper does not mark the day as done.
  6. Single writer — a lock prevents two agents or two Obsidian instances
     from syncing at once.

Usage:
    python3 scripts/vault_sync.py [--vault PATH] [--dry-run] [--allow-branch]
                                  [--skip-secret-scan]

Vault location, in order: --vault, $OBSIDIAN_VAULT, error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# v4 integration. Imported lazily inside `run_v4_check` so the file stays
# usable on a checkout that doesn't ship the protocol module yet (e.g. a
# stack pinned to a tag from before this commit). The v4 enforcement is
# a contract check, not a build-time dependency.
_vault_protocol = None  # populated by _load_vault_protocol()

# The lock lives inside .git/, never in the working tree: a lock file next to
# the notes makes `git status` permanently dirty, so the vault is never "already
# in sync" and the lock ends up committed and pushed with the notes.
LOCK_NAME = "vault-sync.lock"
LOCK_STALE_SECONDS = 900  # 15 min — a sync that long has failed, not stalled

# v4 maintenance sentinel. Distinct from LOCK_NAME: maintenance is a
# human-set signal that says "stay out, the orchestrator is rebuilding
# the vault"; the sync lock is a short-lived single-writer claim.
# Confusing the two would let a long sync trip the maintenance guard
# the orchestrator put in place.
MAINTENANCE_LOCK = Path(".git") / "maintenance.lock"

# How long the v4 validator is allowed to take before the sync gives
# up. The validator is short and local, so this is purely a guard
# against an accidental hang — not a tight budget.
V4_VALIDATOR_TIMEOUT = 30

# Reuse the stack's single owner of credential patterns when it is reachable.
_ANTI_DEBT_TOOLS = Path(__file__).resolve().parent.parent / "stack" / "agents" / "anti-debt" / "tools"


def _load_vault_protocol():
    """Return the protocol module, importing it lazily.

    The protocol ships in the same directory as this script. We import
    on demand so a stack pinned to a tag from before the protocol
    existed still loads — the v4 enforcement is then just absent, not
    broken.
    """
    global _vault_protocol
    if _vault_protocol is not None:
        return _vault_protocol
    try:
        import vault_protocol  # type: ignore  # noqa: PLC0415
    except ImportError:
        return None
    _vault_protocol = vault_protocol
    return _vault_protocol


def _load_secret_patterns() -> list:
    """Credential patterns from finding_common, or a minimal built-in set.

    finding_common.SECRET_PATTERNS is the stack's single owner for these; the
    fallback exists only so the vault sync still guards something when run
    from a detached copy.
    """
    if _ANTI_DEBT_TOOLS.is_dir():
        sys.path.insert(0, str(_ANTI_DEBT_TOOLS))
        try:
            from finding_common import SECRET_PATTERNS  # noqa: PLC0415
            return SECRET_PATTERNS
        except ImportError:
            pass
    return [
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key ID"),
        (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "GitHub token"),
        (re.compile(r"sk_live_[A-Za-z0-9]{20,}"), "Stripe live secret key"),
        (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"), "Private key"),
    ]


class SyncError(Exception):
    """A condition that must stop the sync and be reported to the user."""


class VaultSync:
    def __init__(self, vault: Path, dry_run: bool, allow_branch: bool,
                 skip_secret_scan: bool = False,
                 skip_validator_check: bool = False) -> None:
        self.vault = vault
        self.dry_run = dry_run
        self.allow_branch = allow_branch
        self.skip_secret_scan = skip_secret_scan
        # `--no-validator-check` is the *only* way to bypass the v4
        # contract guard. It is meant for tests and migration tooling,
        # not daily use; the option name makes the intent obvious in
        # the eventual audit log.
        self.skip_validator_check = skip_validator_check
        self.lock_path = vault / ".git" / LOCK_NAME

    # --- git plumbing -----------------------------------------------------

    def git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.vault), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if check and result.returncode != 0:
            raise SyncError(f"git {' '.join(args)} failed: "
                            f"{(result.stderr or result.stdout).strip()}")
        return result.stdout.strip()

    def rev(self, ref: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(self.vault), "rev-parse", "--verify", "-q", ref],
            capture_output=True, text=True,
        )
        return result.stdout.strip() or None

    # --- lock -------------------------------------------------------------

    def acquire_lock(self) -> None:
        if self.lock_path.exists():
            age = time.time() - self.lock_path.stat().st_mtime
            if age < LOCK_STALE_SECONDS:
                holder = self.lock_path.read_text(encoding="utf-8", errors="replace").strip()
                raise SyncError(f"another sync is running (lock held by {holder}, "
                                f"{int(age)}s old). Retry later.")
            print(f"  stale lock ({int(age)}s) — taking over")
        if not self.dry_run:
            self.lock_path.write_text(f"pid={os.getpid()} host={os.environ.get('COMPUTERNAME') or os.uname().nodename}",
                                      encoding="utf-8")

    def release_lock(self) -> None:
        if self.lock_path.exists() and not self.dry_run:
            self.lock_path.unlink()

    # --- checks -----------------------------------------------------------

    def primary_branch(self) -> str:
        """The remote's default branch, however it is named."""
        head = self.rev_symbolic("refs/remotes/origin/HEAD")
        if head:
            return head.rsplit("/", 1)[-1]
        for candidate in ("master", "main"):
            if self.rev(f"refs/remotes/origin/{candidate}"):
                return candidate
        raise SyncError("cannot determine the remote's default branch")

    def rev_symbolic(self, ref: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(self.vault), "symbolic-ref", "-q", ref],
            capture_output=True, text=True,
        )
        return result.stdout.strip() or None

    def allowlist(self) -> list[str]:
        """Literal strings the vault owner has marked as non-secret.

        One per line in `.vault-sync-allow` at the vault root; `#` starts a
        comment. A vault is full of notes *about* credentials, and blocking
        the backup of a second brain forever is worse than the leak risk of a
        string its owner has explicitly reviewed.
        """
        allow_file = self.vault / ".vault-sync-allow"
        if not allow_file.is_file():
            return []
        entries = []
        for line in allow_file.read_text(encoding="utf-8", errors="replace").split("\n"):
            line = line.split("#", 1)[0].strip()
            if line:
                entries.append(line)
        return entries

    @staticmethod
    def _looks_like_placeholder(matched: str) -> bool:
        """True for documented examples and obvious fill-me-in values.

        `AKIAIOSFODNN7EXAMPLE` is AWS's own documentation key and
        `xoxb-your-bot-token` is a Slack placeholder; both match the real
        patterns. Notes that discuss credential formats would otherwise
        block every sync.
        """
        markers = ("example", "your-", "your_", "yourname", "placeholder",
                   "changeme", "change-me", "dummy", "sample", "specimen",
                   "xxxx", "<", "todo", "redacted", "fake")
        lowered = matched.lower()
        return any(marker in lowered for marker in markers)

    def _is_v4_vault(self) -> bool:
        """True when the vault exposes the v4 contract surface.

        Detection is cheap and version-stable: we only look for the
        schema registry and the validator entry point. If those two
        files exist, the rest of the v4 contract is in force and the
        sync must enforce it.
        """
        return (self.vault / "_system" / "schemas" / "projects.json").is_file() \
           and (self.vault / "_system" / "tooling" / "vault.py").is_file()

    def maintenance_locked(self) -> bool:
        """True when the orchestrator's maintenance sentinel is present.

        The sentinel is an empty file at `.git/maintenance.lock`. The
        orchestrator puts it there during Gate 0 to keep two agents
        from racing on the same checkout. The sync must back off until
        the lock is removed, not race past it.
        """
        return (self.vault / MAINTENANCE_LOCK).is_file()

    def run_v4_check(self) -> None:
        """Invoke the vault's v4 validator and refuse to commit on red.

        Mirrors the secret-scan guarantee: a non-zero exit raises a
        `SyncError`, the staged index is reset to its prior state, and
        the user gets the validator's own output so the cause is
        debuggable. The function is a no-op on a non-v4 vault — older
        vaults have no validator to call, and silently skipping would
        erase the contract that distinguishes a v4 sync from any
        other backup.
        """
        if not self._is_v4_vault():
            return
        protocol = _load_vault_protocol()
        if protocol is None:
            # Stack is older than the protocol layer; the user has
            # configured a v4 vault but the sync cannot enforce it.
            # Failing loud is the only safe option.
            raise SyncError(
                "vault is v4 but the stack does not ship vault_protocol.py — "
                "upgrade the stack before syncing a v4 vault."
            )

        status = protocol.check_vault(
            str(self.vault),
            run_validation=True,
            validator_subcommand="check",
            validator_timeout=V4_VALIDATOR_TIMEOUT,
        )
        if status.status == "ok":
            return
        if status.status == "maintenance":
            raise SyncError(
                f"v4 maintenance lock present at {MAINTENANCE_LOCK} — refusing "
                "to sync. Remove the lock when the orchestrator's Gate is done."
            )
        if status.status == "timeout":
            raise SyncError(
                f"v4 validator exceeded {V4_VALIDATOR_TIMEOUT}s — refusing to "
                "commit. The vault is in an unexpected state; investigate before retry."
            )
        if status.status == "validator-down":
            raise SyncError(
                "v4 validator is missing or not executable — refusing to commit. "
                f"Detail: {status.detail}"
            )
        # status == "validator-red" (or any other failure): bail out.
        raise SyncError(
            f"v4 validator refused the vault (status={status.status}): "
            f"{status.detail}"
        )

    def scan_for_secrets(self) -> list[str]:
        """Look for credentials in what is about to be committed."""
        patterns = _load_secret_patterns()
        allowed = self.allowlist()
        hits: list[str] = []
        changed = self.git("diff", "--cached", "--name-only", "--diff-filter=ACM")
        for name in filter(None, changed.split("\n")):
            path = self.vault / name
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(content.split("\n"), start=1):
                for pattern, label in patterns:
                    match = pattern.search(line)
                    if not match:
                        continue
                    value = match.group(0)
                    if self._looks_like_placeholder(value):
                        break
                    if any(entry in line for entry in allowed):
                        break
                    hits.append(f"{name}:{lineno} — {label} ({value[:24]}…)")
                    break
        return hits

    # --- the sync ---------------------------------------------------------

    def run(self) -> int:
        if not (self.vault / ".git").exists():
            print(f"vault: not a git repository ({self.vault}) — skip")
            return 0

        # v4 maintenance check first. It costs one stat() and refuses the
        # whole sync before any fetch or remote access — exactly the
        # behaviour the orchestrator's Gate 0 expects.
        if self.maintenance_locked():
            raise SyncError(
                f"v4 maintenance lock present at {MAINTENANCE_LOCK} — refusing "
                "to sync. Remove the lock when the orchestrator is done."
            )

        # v4 validator runs only when the vault is v4 and the operator
        # has not asked for a legacy run. The function is a no-op on
        # older vaults, so the existing behaviour is preserved.
        if not self.skip_validator_check:
            self.run_v4_check()

        branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        if branch == "HEAD":
            raise SyncError("vault is in detached HEAD state — check out a branch first")

        self.git("fetch", "origin", branch, check=False)
        primary = self.primary_branch()

        if branch != primary and not self.allow_branch:
            raise SyncError(
                f"vault is on branch '{branch}', not '{primary}'.\n"
                f"       A vault has no reason to carry branches, and a side branch is\n"
                f"       how the backup silently stops working. Consolidate first:\n"
                f"         git -C \"{self.vault}\" checkout {primary}\n"
                f"         git -C \"{self.vault}\" merge --ff-only {branch}\n"
                f"       Then re-run. Use --allow-branch only if you know why."
            )

        remote_ref = f"origin/{branch}"
        local = self.rev("HEAD")
        remote = self.rev(remote_ref)
        if remote is None:
            raise SyncError(f"{remote_ref} does not exist — push it once manually first")
        base = self.git("merge-base", "HEAD", remote_ref)

        dirty = bool(self.git("status", "--porcelain"))

        if local == remote and not dirty:
            print("vault: already in sync with the remote")
            return 0

        if base != remote and base != local:
            raise SyncError(
                f"local and {remote_ref} have diverged — nothing was pushed.\n"
                f"       Resolve manually:  git -C \"{self.vault}\" status")

        if base == local and not dirty:
            if self.dry_run:
                print(f"vault: would pull {remote_ref} (behind)")
                return 0
            self.git("pull", "--rebase", "origin", branch)
            print(f"vault: updated from the remote ({remote_ref})")
            return 0

        if dirty:
            self.git("add", "-A")
            secrets = [] if self.skip_secret_scan else self.scan_for_secrets()
            if secrets:
                self.git("reset", check=False)
                raise SyncError(
                    "credential pattern found in staged content — nothing committed "
                    "or pushed:\n       " + "\n       ".join(secrets[:10])
                    + "\n\n       If these are documented examples, either add the "
                      "line's distinctive\n       text to "
                      f"'{self.vault / '.vault-sync-allow'}' (one per line),\n"
                      "       or re-run with --skip-secret-scan for this one sync.")
            if self.dry_run:
                staged = self.git("diff", "--cached", "--name-only")
                count = len([s for s in staged.split("\n") if s])
                self.git("reset", check=False)
                print(f"vault: would commit and push {count} changed file(s)")
                return 0
            stamp = time.strftime("%Y-%m-%d %H:%M")
            self.git("commit", "-m", f"chore(vault): auto-sync {stamp}")

        if self.dry_run:
            print("vault: would push (already committed, unpushed)")
            return 0

        ahead = self.git("rev-list", "--count", f"{remote_ref}..HEAD")
        self.git("push", "origin", branch)

        # Verify rather than assume — this is the check whose absence let a
        # no-op push report success for thirteen days.
        self.git("fetch", "origin", branch, check=False)
        pushed = self.rev(remote_ref)
        head = self.rev("HEAD")
        if pushed != head:
            raise SyncError(f"push reported success but {remote_ref} is still at "
                            f"{(pushed or '?')[:8]} while HEAD is {(head or '?')[:8]} — "
                            f"NOT backed up")

        print(f"vault: pushed to the remote ({ahead} commit(s), branch {branch})")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vault", type=Path, default=None,
                        help="vault path (default: $OBSIDIAN_VAULT)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen, change nothing")
    parser.add_argument("--allow-branch", action="store_true",
                        help="permit syncing a non-primary branch")
    parser.add_argument("--skip-secret-scan", action="store_true",
                        help="bypass the credential guard for this run only")
    parser.add_argument("--no-validator-check", dest="skip_validator_check",
                        action="store_true",
                        help="bypass the v4 vault validator for legacy fixtures "
                             "and tests; never use in production.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    vault = args.vault or (Path(os.environ["OBSIDIAN_VAULT"])
                           if os.environ.get("OBSIDIAN_VAULT") else None)
    if vault is None:
        print("vault: no vault configured — pass --vault or set OBSIDIAN_VAULT",
              file=sys.stderr)
        return 2
    if not vault.is_dir():
        print(f"vault: {vault} not found — skip")
        return 0

    sync = VaultSync(vault.resolve(), args.dry_run, args.allow_branch,
                     args.skip_secret_scan,
                     skip_validator_check=args.skip_validator_check)
    try:
        sync.acquire_lock()
        return sync.run()
    except SyncError as err:
        print(f"vault: {err}", file=sys.stderr)
        return 1
    finally:
        sync.release_lock()


if __name__ == "__main__":
    sys.exit(main())
