"""Detect a new release; apply one transactionally; roll one back.

Three separations matter here and each is load-bearing.

*Detection is not application.* `check` can run automatically. `apply` never
does. The stack changes the instructions an agent obeys; changing those without
being asked is not an update.

*The cache is not the network.* A check consults `update-cache.json` first and
only reaches out when the TTL has expired, so `ainative status` costs nothing
and works offline.

*Authority commands never call any of this.* `verify`, `converge`, `trust` and
`work` are routed by the dispatcher without touching this module: a verdict must
not depend on what a remote server said (ADR-0009 §6).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import installer as installerlib
from . import manifest as manifestlib
from . import provider as providerlib
from . import source as sourcelib
from . import state as statelib
from . import version as versionlib
from .errors import LifecycleError
from .paths import validate_relative
from .source import DistributionSource

UP_TO_DATE = "UP_TO_DATE"
UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
OFFLINE = "OFFLINE"
CHECK_FAILED = "CHECK_FAILED"
DISABLED = "DISABLED"

DISABLE_ENV = "AINATIVE_NO_UPDATE_CHECK"
STAGED_RELATIVE = statelib.LIFECYCLE_DIRNAME / "staged"
ROLLBACK_RELATIVE = statelib.LIFECYCLE_DIRNAME / "rollback.json"

# A zip that expands to more than this, or holds more entries, is refused before
# a single byte is written. Both are classic archive bombs.
MAX_EXPANDED_BYTES = 512 << 20
MAX_ARCHIVE_ENTRIES = 20000


@dataclass
class CheckResult:
    status: str
    current: str
    latest: str | None = None
    notes: str = ""
    from_cache: bool = False
    checked_at: str | None = None
    detail: str = ""

    def to_record(self) -> dict:
        return {"status": self.status, "current": self.current, "latest": self.latest,
                "from_cache": self.from_cache, "checked_at": self.checked_at,
                "detail": self.detail}

    def message(self) -> str:
        if self.status == UPDATE_AVAILABLE:
            return (f"AI Native {self.latest} is available.\nCurrent: {self.current}\n"
                    "Run `ainative update`")
        if self.status == UP_TO_DATE:
            return f"Up to date ({self.current})."
        if self.status == DISABLED:
            return "Update checks are disabled."
        return f"{self.status}: {self.detail}" if self.detail else self.status


def cache_path(project: Path) -> Path:
    return project / statelib.UPDATE_CACHE_RELATIVE


def _read_cache(project: Path) -> dict | None:
    try:
        payload = json.loads(cache_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(project: Path, result: CheckResult) -> None:
    statelib.write_atomic(cache_path(project),
                          json.dumps(result.to_record(), indent=2, sort_keys=True) + "\n")


def _cache_age(payload: dict) -> float | None:
    stamp = payload.get("checked_at")
    if not isinstance(stamp, str):
        return None
    try:
        checked = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - checked).total_seconds()


def checks_disabled(state: statelib.InstallState | None) -> bool:
    if os.environ.get(DISABLE_ENV, "").strip() not in ("", "0", "false", "False"):
        return True
    if state is None:
        return False
    preferences = state.update_preferences
    return not preferences.get("enabled", True) or not preferences.get("auto_check", True)


def check(project: Path, *, force: bool = False, allow_network: bool = True,
          state: statelib.InstallState | None = None,
          source: DistributionSource | None = None) -> CheckResult:
    """Resolve the newest compatible release. Never fatal, never a traceback."""

    project = installerlib.require_project(project)
    state = state if state is not None else statelib.load(project)
    source = source or sourcelib.resolve()
    current = state.stack_version if state else source.version
    channel = (state.update_preferences.get("channel") if state else "stable") or "stable"
    interval = int(state.update_preferences.get("check_interval", 86400)) if state else 86400

    cached = _read_cache(project)
    if cached and not force:
        age = _cache_age(cached)
        if age is not None and age < interval:
            return CheckResult(status=str(cached.get("status", CHECK_FAILED)), current=current,
                               latest=cached.get("latest"), from_cache=True,
                               checked_at=cached.get("checked_at"),
                               detail=str(cached.get("detail", "")))

    if not allow_network or (checks_disabled(state) and not force):
        return CheckResult(DISABLED, current, from_cache=False, detail="update checks disabled")

    try:
        release = providerlib.build(channel).latest(channel)
    except LifecycleError as error:
        status = OFFLINE if error.code == "UPDATE_CHECK_FAILED" else CHECK_FAILED
        result = CheckResult(status, current, detail=error.message,
                             checked_at=statelib.now())
        _write_cache(project, result)
        return result

    newer = versionlib.is_newer(release.version, current)
    result = CheckResult(UPDATE_AVAILABLE if newer else UP_TO_DATE, current,
                         latest=release.version, notes=release.notes,
                         checked_at=statelib.now())
    _write_cache(project, result)
    return result


def cached_notice(project: Path, *, allow_network: bool = False) -> dict | None:
    """What a status line may print. Reads the cache; never dials out by itself."""

    if allow_network:
        return check(project).to_record()
    cached = _read_cache(project)
    if cached is None:
        return None
    return {**cached, "from_cache": True}


# --- applying an update --------------------------------------------------


@dataclass
class UpdateResult:
    applied: bool
    dry_run: bool
    from_version: str
    to_version: str | None
    check: CheckResult
    plan: dict | None = None
    conflicts: list[str] = field(default_factory=list)
    transaction: str | None = None
    rollback_available: bool = False

    def to_record(self) -> dict:
        return {"operation": "update", "applied": self.applied, "dry_run": self.dry_run,
                "from_version": self.from_version, "to_version": self.to_version,
                "check": self.check.to_record(), "plan": self.plan,
                "conflicts": sorted(self.conflicts), "transaction": self.transaction,
                "rollback_available": self.rollback_available}


def _safe_extract(payload: bytes, destination: Path) -> Path:
    """Expand an archive with every name validated before anything is written.

    `ZipFile.extractall` happily writes `../../etc/cron.d/x`. Each entry is
    therefore parsed by the same containment rule that guards every other
    destination, and the total expanded size is bounded.
    """

    destination.mkdir(parents=True, exist_ok=True)
    archive_file = destination / "release.zip"
    archive_file.write_bytes(payload)
    total = 0
    with zipfile.ZipFile(archive_file) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                                 f"archive holds {len(entries)} entries, over the limit")
        for info in entries:
            name = info.filename
            if name.endswith("/"):
                validate_relative(name.rstrip("/"))
                continue
            validate_relative(name)          # refuses .., absolute, drive, NUL
            total += info.file_size
            if total > MAX_EXPANDED_BYTES:
                raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                                     "archive expands beyond the size limit")
        root = destination / "extracted"
        for info in entries:
            if info.is_dir():
                continue
            target = root.joinpath(*validate_relative(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as reader, target.open("wb") as writer:
                shutil.copyfileobj(reader, writer, length=1 << 20)
    archive_file.unlink(missing_ok=True)
    return root


def _distribution_root(extracted: Path) -> Path:
    """A release archive usually wraps everything in one top-level directory."""

    if (extracted / "VERSION").is_file():
        return extracted
    children = [item for item in extracted.iterdir() if item.is_dir()]
    if len(children) == 1 and (children[0] / "VERSION").is_file():
        return children[0]
    raise LifecycleError("UPDATE_INTEGRITY_FAILED",
                         "release archive does not contain a stack distribution")


def _record_rollback(project: Path, state: statelib.InstallState, journal: str,
                     from_version: str, to_version: str) -> None:
    statelib.write_atomic(project / ROLLBACK_RELATIVE, json.dumps({
        "schema_version": 1,
        "transaction": journal,
        "from_version": from_version,
        "to_version": to_version,
        "profile": state.active_profile,
        "recorded_at": statelib.now(),
        "scope": ("project assets only — this record cannot restore a globally "
                  "installed Python package"),
    }, indent=2, sort_keys=True) + "\n")


def apply(project: Path, *, dry_run: bool = False, force: bool = False,
          distribution: manifestlib.Distribution | None = None) -> UpdateResult:
    """check -> resolve -> stage -> verify -> transactional apply -> commit."""

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    state = statelib.load(project)
    if state is None:
        raise LifecycleError("NOT_INSTALLED",
                             f"no AI Native installation recorded in {project}")

    outcome = check(project, force=True, state=state)
    if outcome.status not in (UPDATE_AVAILABLE,) and not force:
        return UpdateResult(applied=False, dry_run=dry_run, from_version=state.stack_version,
                            to_version=outcome.latest, check=outcome)

    channel = state.update_preferences.get("channel", "stable") or "stable"
    provider = providerlib.build(channel)
    release = provider.latest(channel)
    payload = provider.fetch(release)
    providerlib.verify_archive(payload, release.digest)

    staging = Path(tempfile.mkdtemp(prefix="ainative-update-",
                                    dir=str(_staging_root(project))))
    try:
        root = _distribution_root(_safe_extract(payload, staging))
        staged_source = DistributionSource(root=root.resolve(), origin="update",
                                           version=sourcelib.read_version(root))
        plan, _, _ = installerlib.plan_profile(project, distribution, staged_source,
                                               state.active_profile, operation="update",
                                               state=state)
        conflicts = [change.path for change in plan.changes
                     if change.action == "CONFLICT"]
        for path in conflicts:
            _write_side_by_side(project, plan, staged_source, path)

        if dry_run:
            return UpdateResult(False, True, state.stack_version, staged_source.version,
                                outcome, plan.to_record(), conflicts)

        result = installerlib.install(project, state.active_profile, operation="update",
                                      distribution=distribution, source=staged_source)
        if result.transaction:
            _record_rollback(project, state, result.transaction, state.stack_version,
                             staged_source.version)
        return UpdateResult(True, False, state.stack_version, staged_source.version, outcome,
                            result.plan.to_record(), conflicts, result.transaction,
                            rollback_available=bool(result.transaction))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _staging_root(project: Path) -> Path:
    root = project / STAGED_RELATIVE
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_side_by_side(project: Path, plan, source: DistributionSource, path: str) -> None:
    """A file the user changed keeps its content; the new one lands beside it.

    Merging is deliberately not attempted. A deterministic merge of arbitrary
    content is not available here, and an LLM merge has no place in a lifecycle
    core that must produce the same result twice.
    """

    for change in plan.changes:
        if change.path != path or change.source is None:
            continue
        try:
            payload = source.path(change.source).read_bytes()
        except OSError:
            return
        statelib.write_bytes_atomic(project / f"{path}.new", payload)
        return


def rollback(project: Path, *, dry_run: bool = False) -> dict:
    """Undo the last update from its transaction backup.

    Scope is stated rather than implied: this restores the project's installed
    assets. It cannot restore a Python package installed elsewhere on the
    machine, and it does not claim to.
    """

    from . import transaction as txnlib

    project = installerlib.require_project(project)
    record_path = project / ROLLBACK_RELATIVE
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LifecycleError("ROLLBACK_UNAVAILABLE",
                             "no update rollback metadata recorded for this project") from None

    identifier = str(record.get("transaction", ""))
    journals = {item.identifier: item for item in txnlib.read_journals(project)}
    journal = journals.get(identifier)
    if journal is None:
        raise LifecycleError("ROLLBACK_UNAVAILABLE",
                             f"transaction {identifier} is no longer retained; "
                             "its backup has been pruned")
    backup = project / (journal.backup_location or "")
    if not journal.backup_location or not backup.is_dir():
        raise LifecycleError("ROLLBACK_UNAVAILABLE",
                             f"transaction {identifier} kept no backup to restore from")

    # Reversing the update means both halves: files it replaced come back from
    # the backup, and files it *created* go away. Restoring only the first left
    # a project holding the old version's content and the new version's new
    # files, with a state that agreed with neither (EMP-LC-014).
    would_restore = sorted(item["path"] for item in journal.completed_changes
                           if isinstance(item.get("path"), str)
                           and item.get("action") != "CREATE")
    would_remove = sorted(item["path"] for item in journal.completed_changes
                          if isinstance(item.get("path"), str)
                          and item.get("action") == "CREATE")
    if dry_run:
        return {"operation": "update rollback", "dry_run": True,
                "transaction": identifier, "to_version": record.get("from_version"),
                "would_restore": would_restore, "would_remove": would_remove,
                "scope": record.get("scope", "")}

    from . import lock as locklib

    with locklib.acquire(project, "update-rollback"):
        outcome = txnlib.undo(project, journal)
        state = statelib.load(project)
        if state is not None and not outcome["install_state_restored"]:
            # No saved state to put back (a transaction from before this was
            # recorded). Say what we can rather than leaving a stale version.
            state.stack_version = str(record.get("from_version", state.stack_version))
            state.source_version = state.stack_version
            statelib.save(project, state)
        record_path.unlink(missing_ok=True)
    return {"operation": "update rollback", "dry_run": False, "transaction": identifier,
            "to_version": record.get("from_version"), "restored": outcome["restored"],
            "removed": outcome["removed"],
            "install_state_restored": outcome["install_state_restored"],
            "scope": record.get("scope", "")}


__all__ = [
    "UP_TO_DATE", "UPDATE_AVAILABLE", "OFFLINE", "CHECK_FAILED", "DISABLED", "DISABLE_ENV",
    "CheckResult", "check", "cached_notice", "checks_disabled",
    "UpdateResult", "apply", "rollback", "cache_path", "ROLLBACK_RELATIVE",
    "MAX_EXPANDED_BYTES", "MAX_ARCHIVE_ENTRIES",
]
