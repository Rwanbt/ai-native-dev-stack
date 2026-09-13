"""Machine-level ownership: what the global installer wrote, its health and its
reversal — owned by the package, not by a checkout script.

`ainative machine` and `scripts/install_agents.py` are two frontends over the
same record and the same rules; there is no second implementation to drift.
The manifest lives in one canonical place, `~/.ai-native/machine.json`:

* a **link** is ours when it resolves to the recorded source;
* a **rendered file** is ours when its bytes still hash to the recorded digest;
* a **block** is ours while exactly one BEGIN/END marker pair is present.

Reversal never guesses: a file we never wrote is never touched, and a file we
wrote that the user has since changed is preserved, not deleted. Repair follows
the same proof rule — it only re-creates what the manifest proves this stack
installed and only while the recorded source of truth still exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
MANIFEST_RELATIVE = Path(".ai-native") / "machine.json"

METHOD_BEGIN = "<!-- BEGIN AI-NATIVE-DEV-STACK -->"
METHOD_END = "<!-- END AI-NATIVE-DEV-STACK -->"
VAULT_BEGIN = "<!-- BEGIN AI-NATIVE-DEV-STACK VAULT -->"
VAULT_END = "<!-- END AI-NATIVE-DEV-STACK VAULT -->"

# Directories that exist on a machine whether or not this stack touched them.
# The uninstall prunes empty directories it emptied, but stops here: an empty
# `~/.config` is not ours to remove just because it is empty.
STOP_DIRECTORY_NAMES = frozenset({".config", ".local", ".cache", ".agents",
                                  ".claude", ".codex", ".cursor", ".gemini",
                                  ".mavis", ".ai-native"})

STATE_OK = "OK"
STATE_MISSING = "MISSING"
STATE_MODIFIED = "MODIFIED"
STATE_DRIFTED = "DRIFTED"
STATE_MALFORMED = "MALFORMED"
STATE_UNKNOWN = "UNKNOWN"

PROBLEM_STATES = (STATE_MISSING, STATE_MODIFIED, STATE_DRIFTED,
                  STATE_MALFORMED, STATE_UNKNOWN)


class MachineLifecycleError(RuntimeError):
    """The manifest is unreadable; refusing rather than guessing."""


def manifest_path(home: Path) -> Path:
    return Path(home) / MANIFEST_RELATIVE


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str | None:
    try:
        return _digest_bytes(path.read_bytes())
    except OSError:
        return None


def load(home: Path) -> dict | None:
    path = manifest_path(home)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MachineLifecycleError(f"cannot read {path}: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise MachineLifecycleError(f"{path} is not a machine manifest")
    schema = payload.get("schema_version", 1)
    if not isinstance(schema, int) or schema > SCHEMA_VERSION:
        raise MachineLifecycleError(
            f"{path} uses machine manifest schema {schema}; this CLI understands "
            f"up to {SCHEMA_VERSION}. Upgrade the stack to read it, or remove "
            f"the manifest to start fresh.")
    payload.setdefault("schema_version", 1)
    return payload


def save(home: Path, *, version: str, assets: list[dict],
         stack_root: str | None = None) -> Path:
    path = manifest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": SCHEMA_VERSION,
        "installed_by": "ainative machine",
        "stack_version": version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "assets": sorted(assets, key=lambda item: (item.get("kind", ""),
                                                   item.get("path", ""))),
    }
    if stack_root:
        record["stack_root"] = stack_root
    # Written beside the target then renamed: a crash mid-write leaves the
    # previous manifest intact, never a truncated one (a manifest nobody can
    # read is a manifest nobody can act on).
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)
    return path


def method_block_text(stack: Path, heading: str) -> str:
    """The one method block every harness receives; builder owned here so the
    installer and the repair path cannot disagree about what it says."""

    return (
        f"{METHOD_BEGIN}\n"
        f"## {heading}\n\n"
        f"Read `{Path(stack) / 'AGENTS.md'}` immediately at session start and treat it "
        "as mandatory shared engineering instructions.\n"
        f"{METHOD_END}"
    )


def vault_block_text(vault: Path, slug: str) -> str:
    """The vault-governance block: a pointer to the vault, never a copy."""

    vault = Path(vault)
    rel_root = (vault / "AGENTS.md").as_posix()
    registry = (vault / "_system" / "schemas" / "projects.json").as_posix()
    return (
        f"{VAULT_BEGIN}\n"
        "## Vault governance (v4)\n\n"
        f"This session is bound to the v4 vault at `{vault}`.\n\n"
        f"- Read `{rel_root}` first.\n"
        f"- Resolve the current project slug from the checkout's `AGENTS.md` or "
        f"an explicit per-session `$OBSIDIAN_PROJECT_SLUG`, then validate it in "
        f"`{registry}`. Never reuse a slug from another checkout.\n"
        "- Read `projects/<slug>/AGENTS.md` for project Vault conventions.\n"
        f"- Project notes, sessions, decisions, research and generated views provide "
        "historical/contextual memory. GitHub Issues are the canonical active "
        "work state and own current scope, status, priority, assignee and backlog.\n"
        f"- Generated `projects/<slug>/BOARD.md` and `BOARD.json` are historical/generated "
        "navigation context only; they never override current GitHub state.\n"
        f"- Never edit generated `BOARD.md`/`BOARD.json` projections directly. "
        "Only change `_system/` when the task explicitly targets vault governance. "
        "Never create a Vault task/card because GitHub state is unavailable; surface "
        "`GITHUB_STATE_UNAVAILABLE` instead.\n"
        f"- Vault location and validator status use `$OBSIDIAN_VAULT`. A project "
        "slug is session-local; if it cannot be resolved safely, ask the user.\n"
        f"{VAULT_END}"
    )

def _prune_empty_parents(target: Path, home: Path) -> None:
    """Remove the directories an uninstall emptied, and only those."""

    current = target.parent
    while True:
        if current == home or current.name in STOP_DIRECTORY_NAMES:
            return
        try:
            if not current.is_dir():
                return
            next(current.iterdir())
            return                     # not empty: something else lives here
        except StopIteration:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent


def _asset_path(home: Path, asset: dict) -> Path | None:
    relative = asset.get("path")
    if not isinstance(relative, str) or not relative:
        return None
    return Path(home) / relative


def _relative(home: Path, target: Path) -> str:
    try:
        return target.relative_to(home).as_posix()
    except ValueError:
        return str(target)


def _create_link(source: Path, target: Path) -> tuple[bool, str]:
    """Symlink, falling back to a Windows junction when symlinks are denied.

    Creating a symlink on Windows needs admin rights or Developer Mode. A
    directory junction needs neither and resolves identically for our purposes.
    """

    try:
        target.symlink_to(source, target_is_directory=source.is_dir())
        return True, ""
    except OSError as error:
        if os.name != "nt" or not source.is_dir():
            return False, f"{type(error).__name__}: {error}"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(target), str(source)],
        capture_output=True, text=True,
    )
    if completed.returncode == 0:
        return True, ""
    return False, (completed.stderr or completed.stdout).strip()


def _remove_link(target: Path, source: Path, *, dry_run: bool = False) -> str:
    """REMOVED, MISSING or PRESERVED — never follows the link."""

    if not target.exists() and not target.is_symlink():
        return "MISSING"
    try:
        if target.resolve() != source:
            return "PRESERVED"
    except OSError:
        return "PRESERVED"
    if dry_run:
        return "REMOVED"
    try:
        if target.is_symlink():
            target.unlink()
            return "REMOVED"
        if target.is_dir():
            # A Windows junction: remove the reparse point, never the source.
            target.rmdir()
            return "REMOVED"
        target.unlink()
        return "REMOVED"
    except OSError:
        return "PRESERVED"


def _remove_render(target: Path, recorded: str | None, *, dry_run: bool = False) -> str:
    if not target.is_file():
        return "MISSING"
    if digest_file(target) != recorded:
        return "PRESERVED"        # the user edited it; it is theirs now
    if dry_run:
        return "REMOVED"
    try:
        target.unlink()
        return "REMOVED"
    except OSError:
        return "PRESERVED"


def _remove_block(target: Path, begin: str, end: str, *, dry_run: bool = False) -> str:
    if not target.is_file():
        return "MISSING"
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "PRESERVED"
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        return "MISSING"
    if begin_count != 1 or end_count != 1:
        return "PRESERVED"        # malformed: not a block this code wrote
    start = text.find(begin)
    finish = text.find(end, start + len(begin))
    if finish < 0:
        return "PRESERVED"
    finish += len(end)
    remaining = (text[:start] + text[finish:]).lstrip("\n")
    if dry_run:
        return "REMOVED"
    if not remaining.strip():
        try:
            target.unlink()
            return "REMOVED"
        except OSError:
            return "PRESERVED"
    try:
        target.write_text(remaining if remaining.endswith("\n") else remaining + "\n",
                          encoding="utf-8")
        return "REMOVED"          # the block is removed; the file stays
    except OSError:
        return "PRESERVED"

def uninstall(home: Path, *, dry_run: bool = False) -> dict:
    """Reverse the recorded machine installation. Never guesses beyond the file."""

    home = Path(home)
    manifest = load(home)
    if manifest is None:
        return {"operation": "machine uninstall", "dry_run": dry_run,
                "removed": [], "preserved": [], "missing": [],
                "detail": "no machine manifest: nothing is recorded as ours"}

    removed: list[str] = []
    preserved: list[str] = []
    missing: list[str] = []
    block_candidates: list[tuple[Path, str]] = []
    for asset in manifest["assets"]:
        target = _asset_path(home, asset)
        if target is None:
            preserved.append(str(asset))
            continue
        relative = _relative(home, target)
        kind = asset.get("kind")
        if dry_run:
            # Describe, do not act: the reported class is what a real run would do.
            if kind == "link":
                outcome = _remove_link(target, Path(str(asset.get("source", ""))),
                                       dry_run=True)
            elif kind == "rendered":
                outcome = _remove_render(target, asset.get("digest"), dry_run=True)
            elif kind == "block":
                outcome = _remove_block(target, str(asset.get("begin", "")),
                                        str(asset.get("end", "")), dry_run=True)
                block_candidates.append((target, str(asset.get("preamble", ""))))
            else:
                outcome = "PRESERVED"
        elif kind == "link":
            outcome = _remove_link(target, Path(str(asset.get("source", ""))))
        elif kind == "rendered":
            outcome = _remove_render(target, asset.get("digest"))
        elif kind == "block":
            outcome = _remove_block(target, str(asset.get("begin", "")),
                                    str(asset.get("end", "")))
            block_candidates.append((target, str(asset.get("preamble", ""))))
        else:
            outcome = "PRESERVED"
        if outcome == "REMOVED":
            removed.append(relative)
            if not dry_run:
                _prune_empty_parents(target, home)
        elif outcome == "MISSING":
            missing.append(relative)
        else:
            preserved.append(relative)

    # A file whose only remaining content is the preamble this installer wrote
    # was ours entirely; leaving it behind is residue a user cannot classify.
    seen_candidates: set[str] = set()
    for target, preamble in block_candidates:
        key = str(target)
        if key in seen_candidates or not target.is_file():
            continue
        seen_candidates.add(key)
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        stripped = content.strip()
        if stripped and stripped != preamble.strip():
            continue                    # user content remains: the file stays
        if not dry_run:
            try:
                target.unlink()
            except OSError:
                continue
            _prune_empty_parents(target, home)
        relative = _relative(home, target)
        if relative not in removed:
            removed.append(relative)

    record = {"operation": "machine uninstall", "dry_run": dry_run,
              "removed": sorted(removed), "preserved": sorted(preserved),
              "missing": sorted(missing), "stack_version": manifest.get("stack_version")}
    if not dry_run:
        try:
            manifest_path(home).unlink(missing_ok=True)
        except OSError:
            record["manifest"] = "could not be removed; re-run uninstall"
    return record


__all__ = ["SCHEMA_VERSION", "MANIFEST_RELATIVE", "METHOD_BEGIN", "METHOD_END",
           "VAULT_BEGIN", "VAULT_END", "STOP_DIRECTORY_NAMES",
           "STATE_OK", "STATE_MISSING", "STATE_MODIFIED", "STATE_DRIFTED",
           "STATE_MALFORMED", "STATE_UNKNOWN", "PROBLEM_STATES",
           "MachineLifecycleError", "manifest_path", "load", "save",
           "digest_file", "method_block_text", "vault_block_text",
           "_create_link", "_asset_path", "_relative",
           "_create_link", "uninstall"]
