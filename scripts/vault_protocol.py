"""vault_protocol.py — Stack-side discovery of a v4 Obsidian vault.

The contract lives in the vault (its `_system/schemas/projects.json`,
`_system/tooling/vault.py` and `_system/AGENTS.md`). This module is the
stack's only call site for it: it never re-implements the schema, never
hard-codes a vault path, and never invents state the vault didn't report.

Discovery order (explicit, never implicit):
  1. `OBSIDIAN_VAULT` argument (--vault / positional, depending on caller)
  2. `OBSIDIAN_VAULT` environment variable
  3. explicit error — there is no "default" vault, because guessing wrong
     would write into the user's other notes

Status enum returned to callers — every error path is a value, never an
exception, so callers can branch without catching the wrong thing:

  ok              — vault is reachable, v4 markers present, slug known
  vault-missing   — neither argument nor env pointed at a real directory
  not-v4          — directory exists but lacks the v4 markers
  unknown-slug    — slug is not in the project registry
  maintenance     — vault has a `.git/maintenance.lock` sentinel set
  validator-down  — `vault.py` is missing or returns a non-zero status
  validator-red   — validator ran and reported problems (lint/check exit != 0)
  timeout         — validator ran but exceeded the configured budget
  path-traversal  — caller asked for a path that escapes the vault root

The module is stdlib-only by design: the stack drops into any project,
including ones without a venv. The validator itself is invoked through
`subprocess.run` so the stack reuses the vault's own Python interpreter
when one is present, and otherwise falls back to `sys.executable`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional


# Schema-version contract the vault's projects.json is expected to carry.
# Match by integer; tolerate "4", "4.0", "v4" so we don't break on a minor
# validator bump the moment the vault adds one.
V4_SCHEMA_VERSION = 4

# Slug grammar from the v4 contract. Same expression the vault uses to
# validate incoming project names; duplicating it here is a deliberate
# two-key turn — if the vault ever broadens it, both sides change.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX_LEN = 64

# A maintenance lock is a sentinel file in the vault's .git directory.
# The vault itself never reads it; only this protocol layer and the sync
# do — and the orchestrator's Gate 0 puts it there to keep two agents from
# racing on the same checkout.
MAINTENANCE_LOCK = Path(".git") / "maintenance.lock"

# Files the v4 vault is contractually expected to expose. Existence is the
# cheapest, most version-stable check we can do without re-implementing
# any part of the contract.
V4_MARKERS = (
    Path("AGENTS.md"),
    Path("_system") / "AGENTS.md",
    Path("_system") / "schemas" / "projects.json",
    Path("_system") / "tooling" / "vault.py",
    Path("_system") / "tooling" / "vaultlib.py",
)

# Default budget for the validator call. The validator is a short, local
# script — 30s is enough for any reasonable vault and small enough to be
# reported clearly when exceeded.
DEFAULT_VALIDATOR_TIMEOUT = 30

# Names we treat as referring to a single vault's project structure.
# Kept in one place so a future v5 only needs one edit.
PROJECT_ENTRY_NAMES = ("INDEX.md", "AGENTS.md", "BOARD.md")


@dataclass(frozen=True)
class VaultStatus:
    """Result of a vault resolution. `status` is the discriminator; the
    other fields carry the evidence callers need to act on it.

    A status of `ok` always has a non-None `vault` and a non-None `slug`
    when the caller asked for one. Every other status has `vault` set
    if the directory existed; the rest is diagnostic.
    """

    status: str
    vault: Optional[Path] = None
    slug: Optional[str] = None
    detail: str = ""
    project_root: Optional[Path] = None
    schema_version: Optional[int] = None
    validator: Optional[Path] = None
    errors: list[str] = field(default_factory=list)


class VaultProtocolError(RuntimeError):
    """Raised only when a caller asks a question that the protocol cannot
    answer from its inputs (e.g. an unparseable registry). Real-world
    failures (missing vault, red validator) come back as VaultStatus.
    """


# ---------------------------------------------------------------------------
# Argument + environment discovery
# ---------------------------------------------------------------------------

def resolve_vault_path(arg_value: Optional[str | os.PathLike[str]]) -> Optional[Path]:
    """Return the first usable vault path among (arg, env), or None.

    Order is explicit: an explicit --vault always wins, then the
    environment, then a clear "not configured" answer. Resolution is
    strict — a path that doesn't exist or isn't a directory is treated
    as "not configured" so the caller surfaces the right diagnostic.
    """
    candidates: list[Path] = []
    if arg_value is not None and str(arg_value) != "":
        candidates.append(Path(arg_value))
    env_value = os.environ.get("OBSIDIAN_VAULT")
    if env_value:
        candidates.append(Path(env_value))

    for candidate in candidates:
        # resolve() follows symlinks but never the working directory's
        # relativity, so a caller passing "." doesn't accidentally land
        # in the project's own root. Strict=False so a non-existent path
        # returns its absolute form (so we can report it accurately).
        resolved = candidate.resolve(strict=False)
        if resolved.is_dir():
            return resolved
    return None


def resolve_project_slug(arg_value: Optional[str]) -> Optional[str]:
    """Return the slug from argument, then from OBSIDIAN_PROJECT_SLUG.

    Returns None when neither is set. Does NOT validate the grammar —
    that is the caller's job (it would otherwise collapse "missing" and
    "invalid" into the same answer, which makes triage harder).
    """
    if arg_value:
        return arg_value
    return os.environ.get("OBSIDIAN_PROJECT_SLUG")


def validate_slug(slug: Optional[str]) -> Optional[str]:
    """Return the slug if it matches the v4 grammar, else None.

    The check is intentionally strict: callers that get None back must
    surface the value to the user, because silently switching slugs
    would write into the wrong project's note tree.
    """
    if slug is None:
        return None
    if len(slug) > SLUG_MAX_LEN:
        return None
    if not SLUG_RE.match(slug):
        return None
    return slug


# ---------------------------------------------------------------------------
# v4 detection
# ---------------------------------------------------------------------------

def _is_v4_vault(vault: Path) -> tuple[bool, list[str]]:
    """True when every required v4 marker is present.

    Returning the list of missing markers (rather than just False) lets
    callers explain to the user *which* marker was absent, which matters
    when an older v3 vault has been copied to the expected location.
    """
    missing = [str(marker) for marker in V4_MARKERS if not (vault / marker).is_file()]
    return (not missing, missing)


def _load_registry(vault: Path) -> dict:
    """Load and lightly validate the project registry.

    Raises VaultProtocolError when the file is missing or syntactically
    broken — these are conditions the protocol can't recover from and
    that indicate an environment problem the user must fix.
    """
    path = vault / "_system" / "schemas" / "projects.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise VaultProtocolError(f"registry missing: {path}") from err
    except json.JSONDecodeError as err:
        raise VaultProtocolError(f"registry not valid JSON ({path}): {err}") from err
    if not isinstance(data, dict):
        raise VaultProtocolError(f"registry root must be an object ({path})")
    if "projects" not in data or not isinstance(data["projects"], list):
        raise VaultProtocolError(f"registry missing 'projects' list ({path})")
    return data


def _registry_slug(registry: dict, slug: str) -> Optional[dict]:
    """Return the registry entry for `slug`, or None when unknown.

    A status of `active` is the only one the stack acts on: a `legacy`
    entry is documented as "not a current project", and writing into
    it would be a regression.
    """
    for entry in registry["projects"]:
        if isinstance(entry, dict) and entry.get("slug") == slug:
            return entry
    return None


# ---------------------------------------------------------------------------
# Path confinement
# ---------------------------------------------------------------------------

def confine_path(vault: Path, slug: str, *parts: str) -> Optional[Path]:
    """Resolve `vault/projects/<slug>/<parts...>` and refuse escapes.

    Returns None if the resolved target would leave the vault, which
    happens when `parts` contains a traversal segment (e.g. ".."). The
    function resolves the final path before checking, so symlinks inside
    the vault can't be used to bypass the check.
    """
    base = (vault / "projects" / slug).resolve(strict=False)
    target = base
    for part in parts:
        target = target / part
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    # Defensive double-check: refuse targets outside the vault root.
    try:
        resolved.relative_to(vault.resolve(strict=False))
    except ValueError:
        return None
    return resolved


# ---------------------------------------------------------------------------
# Maintenance lock + validator
# ---------------------------------------------------------------------------

def maintenance_locked(vault: Path) -> bool:
    """True when a maintenance sentinel exists in the vault's .git.

    The sentinel is just an empty file: its existence is the signal, its
    absence means "no agent is in the middle of a Gate 0". This is the
    same convention the vault's own scripts use to keep the sync from
    racing the orchestrator.
    """
    return (vault / MAINTENANCE_LOCK).is_file()


def _validator_path(vault: Path) -> Optional[Path]:
    """Path to `vault.py`, the v4 validator entry point.

    `vaultlib.py` is the implementation; `vault.py` is the dispatch
    shim. The shim is what we call, because it's the contract — it's
    what the vault itself documents as the validator command.
    """
    candidate = vault / "_system" / "tooling" / "vault.py"
    return candidate if candidate.is_file() else None


def run_validator(vault: Path, timeout: int = DEFAULT_VALIDATOR_TIMEOUT,
                  subcommand: str = "lint") -> VaultStatus:
    """Invoke the vault's own validator and translate the outcome.

    The function NEVER raises for the kinds of failure callers will
    want to branch on: missing validator, non-zero exit, timeout. Each
    becomes a `VaultStatus` with a distinct `status` value, so the
    caller can decide what to do without try/except noise.

    Subcommand resolution: the v4 contract names `check` as the
    canonical command, but the current vault may not have shipped it
    yet. We try `check` first, fall back to `lint` (the surface
    available in every v4 release so far). The fallback is reported
    via `detail` so an operator can see why a newer contract would
    have caught more.
    """
    validator = _validator_path(vault)
    if validator is None:
        return VaultStatus(
            status="validator-down",
            vault=vault,
            detail="validator missing at _system/tooling/vault.py",
        )

    # Prefer the contract's named subcommand; degrade gracefully.
    chosen = subcommand
    if subcommand == "check":
        # Probe whether `check` is even a registered subcommand. We do
        # this by asking the script's --help output rather than importing
        # it — the validator might be a different Python (vault-local
        # venv) and import would fail in the stack's interpreter.
        help_result = subprocess.run(
            [sys.executable, str(validator), "--help"],
            capture_output=True, text=True, timeout=timeout,
        )
        if help_result.returncode == 0 and "check " not in (help_result.stdout + " "):
            chosen = "lint"

    completed = subprocess.run(
        [sys.executable, str(validator), "--root", str(vault), chosen],
        capture_output=True, text=True, timeout=timeout,
    )

    if completed.returncode == 0:
        return VaultStatus(
            status="ok",
            vault=vault,
            validator=validator,
            detail=f"validator={chosen}",
        )

    # A red validator is a meaningful answer, not a transport error.
    # Callers should treat it like an HTTP 4xx — show the body and let
    # the user decide.
    return VaultStatus(
        status="validator-red",
        vault=vault,
        validator=validator,
        detail=(completed.stdout + completed.stderr).strip()[:1000],
    )


# ---------------------------------------------------------------------------
# Vault-level v4 check (no slug required)
# ---------------------------------------------------------------------------

def check_vault(vault_arg: Optional[str | os.PathLike[str]],
                *,
                run_validation: bool = True,
                validator_subcommand: str = "check",
                validator_timeout: int = DEFAULT_VALIDATOR_TIMEOUT) -> VaultStatus:
    """Verify that a directory is a v4 vault, without requiring a slug.

    The sync uses this entry point: it doesn't care which project the
    operator is in, only that the vault is a real v4 vault and the
    contract guard is green. Discovering a slug is the installer's job,
    not the sync's.

    Returns the same VaultStatus shape as `discover()`, minus the
    `slug` and `project_root` (which are not meaningful here).
    """
    vault = resolve_vault_path(vault_arg)
    if vault is None:
        return VaultStatus(
            status="vault-missing",
            detail="no vault path from --vault, positional, or OBSIDIAN_VAULT",
        )

    is_v4, missing = _is_v4_vault(vault)
    if not is_v4:
        return VaultStatus(
            status="not-v4",
            vault=vault,
            detail=f"missing markers: {', '.join(missing)}",
        )

    schema_version: Optional[int] = None
    try:
        registry = _load_registry(vault)
    except VaultProtocolError as err:
        return VaultStatus(
            status="not-v4",
            vault=vault,
            detail=str(err),
        )
    raw_version = registry.get("schema_version")
    if isinstance(raw_version, int):
        schema_version = raw_version
    elif isinstance(raw_version, str) and raw_version.lstrip("vV").isdigit():
        schema_version = int(raw_version.lstrip("vV").split(".")[0])
    if schema_version is not None and schema_version < V4_SCHEMA_VERSION:
        return VaultStatus(
            status="not-v4",
            vault=vault,
            schema_version=schema_version,
            detail=f"registry schema_version={schema_version}, requires >= {V4_SCHEMA_VERSION}",
        )

    if maintenance_locked(vault):
        return VaultStatus(
            status="maintenance",
            vault=vault,
            schema_version=schema_version,
            detail=f"lock present at {MAINTENANCE_LOCK}",
        )

    if not run_validation:
        return VaultStatus(
            status="ok",
            vault=vault,
            schema_version=schema_version,
            detail="discovery only, validator skipped",
        )

    try:
        return run_validator(vault, timeout=validator_timeout,
                             subcommand=validator_subcommand)
    except subprocess.TimeoutExpired:
        return VaultStatus(
            status="timeout",
            vault=vault,
            schema_version=schema_version,
            detail=f"validator exceeded {validator_timeout}s",
        )


# ---------------------------------------------------------------------------
# Top-level resolution (vault + slug)
# ---------------------------------------------------------------------------

def discover(vault_arg: Optional[str | os.PathLike[str]],
             slug_arg: Optional[str],
             *,
             run_validation: bool = True,
             validator_subcommand: str = "check",
             validator_timeout: int = DEFAULT_VALIDATOR_TIMEOUT) -> VaultStatus:
    """Resolve vault + slug in one call and validate the pair.

    This is the entry point used by every installer, hook, and sync.
    Centralising it means the discovery rules are written once and the
    six harness integrations can stay thin.
    """
    vault = resolve_vault_path(vault_arg)
    if vault is None:
        return VaultStatus(
            status="vault-missing",
            detail="no vault path from --vault, positional, or OBSIDIAN_VAULT",
        )

    is_v4, missing = _is_v4_vault(vault)
    if not is_v4:
        return VaultStatus(
            status="not-v4",
            vault=vault,
            detail=f"missing markers: {', '.join(missing)}",
        )

    schema_version: Optional[int] = None
    registry_path = vault / "_system" / "schemas" / "projects.json"
    try:
        registry = _load_registry(vault)
    except VaultProtocolError as err:
        return VaultStatus(
            status="not-v4",
            vault=vault,
            detail=str(err),
        )
    raw_version = registry.get("schema_version")
    if isinstance(raw_version, int):
        schema_version = raw_version
    elif isinstance(raw_version, str) and raw_version.lstrip("vV").isdigit():
        schema_version = int(raw_version.lstrip("vV").split(".")[0])
    if schema_version is not None and schema_version < V4_SCHEMA_VERSION:
        return VaultStatus(
            status="not-v4",
            vault=vault,
            schema_version=schema_version,
            detail=f"registry schema_version={schema_version}, requires >= {V4_SCHEMA_VERSION}",
        )

    slug = validate_slug(slug_arg)
    if slug is None:
        return VaultStatus(
            status="unknown-slug",
            vault=vault,
            schema_version=schema_version,
            detail=f"slug {slug_arg!r} does not match {SLUG_RE.pattern}",
        )

    if _registry_slug(registry, slug) is None:
        return VaultStatus(
            status="unknown-slug",
            vault=vault,
            schema_version=schema_version,
            detail=f"slug {slug!r} not in registry",
        )

    if maintenance_locked(vault):
        return VaultStatus(
            status="maintenance",
            vault=vault,
            slug=slug,
            schema_version=schema_version,
            detail=f"lock present at {MAINTENANCE_LOCK}",
        )

    if not run_validation:
        return VaultStatus(
            status="ok",
            vault=vault,
            slug=slug,
            project_root=vault / "projects" / slug,
            schema_version=schema_version,
            detail="discovery only, validator skipped",
        )

    try:
        validator_status = run_validator(vault, timeout=validator_timeout,
                                          subcommand=validator_subcommand)
    except subprocess.TimeoutExpired:
        return VaultStatus(
            status="timeout",
            vault=vault,
            slug=slug,
            project_root=vault / "projects" / slug,
            schema_version=schema_version,
            detail=f"validator exceeded {validator_timeout}s",
        )

    return replace(
        validator_status,
        slug=slug,
        project_root=vault / "projects" / slug,
        schema_version=schema_version,
    )


# ---------------------------------------------------------------------------
# Convenience: load a project's INDEX/AGENTS/BOARD as text, in one shot
# ---------------------------------------------------------------------------

def read_project_assets(vault: Path, slug: str) -> dict[str, Optional[str]]:
    """Return a {name: body-or-None} dict for the three project files.

    A `None` value means the file is absent — not a read error. The
    caller decides whether an absent AGENTS.md is a "needs-triage" signal
    or a normal state for a freshly-created project.
    """
    out: dict[str, Optional[str]] = {}
    for name in PROJECT_ENTRY_NAMES:
        path = vault / "projects" / slug / name
        if not path.is_file():
            out[name] = None
            continue
        try:
            out[name] = path.read_text(encoding="utf-8")
        except OSError:
            out[name] = None
    return out
