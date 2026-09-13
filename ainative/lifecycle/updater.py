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

*The runtime is the policy.* Applying release N+1 is done by the lifecycle code
of N+1: the manifests, the planner and the transaction engine all ship inside
the Python package, so a project whose assets were minted by a newer release
would be maintained by an older policy that cannot know them. `apply` therefore
refuses any target whose version differs from the running package
(`CLI_UPDATE_REQUIRED`), before downloading and before the first write. This is
strict equality on purpose: a compatibility matrix no release has needed yet
would be a silent permission system, and a silent permission system is what
this refusal exists to remove.
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
from . import planner as plannerlib
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
UPGRADE_COMMAND_TEMPLATE = (
    'pip install --upgrade '
    '"git+https://github.com/Rwanbt/ai-native-dev-stack.git@v{version}"')

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
    # Whether THIS runtime could apply `latest`. Recomputed from the running
    # package at every read - never trusted from a cache written by another
    # runtime, which is the stale-notice class this avoids (#131).
    runtime_version: str = ""
    runtime_ready: bool = True

    def to_record(self) -> dict:
        return {"status": self.status, "current": self.current, "latest": self.latest,
                "from_cache": self.from_cache, "checked_at": self.checked_at,
                "detail": self.detail, "runtime_version": self.runtime_version,
                "runtime_ready": self.runtime_ready}

    def message(self) -> str:
        if self.status == UPDATE_AVAILABLE:
            lines = [f"AI Native {self.latest} is available.",
                     f"Current: {self.current}"]
            if self.runtime_ready:
                lines.append("Run `ainative update`")
            else:
                lines.append(f"This CLI runtime is {self.runtime_version}; release "
                             f"{self.latest} must be applied by runtime {self.latest}.")
                lines.append(f"Upgrade the CLI first: {upgrade_command(str(self.latest))}")
            return "\n".join(lines)
        if self.status == UP_TO_DATE:
            return f"Up to date ({self.current})."
        if self.status == DISABLED:
            return "Update checks are disabled."
        return f"{self.status}: {self.detail}" if self.detail else self.status


def cache_path(project: Path) -> Path:
    return project / statelib.UPDATE_CACHE_RELATIVE


def runtime_version() -> str:
    """The version of the package executing this code - not of any release."""

    from ainative import __version__

    return __version__


def upgrade_command(version: str) -> str:
    """The exact command that installs the runtime a target release needs."""

    return UPGRADE_COMMAND_TEMPLATE.format(version=version)


def _runtime_fields(result: CheckResult) -> CheckResult:
    """Fill the freshness fields from the running package, every time."""

    runtime = runtime_version()
    result.runtime_version = runtime
    result.runtime_ready = (result.status != UPDATE_AVAILABLE
                            or result.latest is None
                            or runtime == result.latest)
    return result


def _reconcile_cached(cached: dict, current: str) -> CheckResult:
    """Read a cached answer without letting it outrank the state it describes.

    A cache written before an update lands still says UPDATE_AVAILABLE for the
    version the project just moved to, and `update check` then announces
    "2.2.1 is available. Current: 2.2.1" until the TTL expires (#131). The
    comparison happens at every read, so the answer is corrected immediately
    without mutating the cache - some readers are read-only by contract.

    A cached value that is not SemVer cannot establish "newer", and the
    failure this guards against is announcing an update that is not one, so it
    resolves to UP_TO_DATE with the reason stated in `detail`.
    """

    status = str(cached.get("status", CHECK_FAILED))
    latest = cached.get("latest")
    detail = str(cached.get("detail", ""))
    if status == UPDATE_AVAILABLE:
        if not (isinstance(latest, str) and versionlib.parse(latest) is not None):
            status = UP_TO_DATE
            detail = "cached availability notice carries no usable version"
        elif not versionlib.is_newer(latest, current):
            status = UP_TO_DATE
            detail = f"cached availability notice ({latest}) is not newer than {current}"
    result = CheckResult(status=status, current=current,
                         latest=latest if isinstance(latest, str) else None,
                         from_cache=True, checked_at=cached.get("checked_at"),
                         detail=detail)
    return _runtime_fields(result)


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
          record: bool = True, state: statelib.InstallState | None = None,
          source: DistributionSource | None = None,
          release: providerlib.Release | None = None) -> CheckResult:
    """Resolve the newest compatible release. Never fatal, never a traceback.

    `record=False` answers without touching the cache. `update --dry-run` needs
    it: the cache is a file, and a dry run that wrote one was a dry run that
    changed the project (EMP-LC-024).

    `release` lets a caller that already resolved the release (the updater,
    which must check the runtime contract before any write) share it instead of
    asking the provider twice.
    """

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
            return _reconcile_cached(cached, current)

    if not allow_network or (checks_disabled(state) and not force):
        return _runtime_fields(CheckResult(DISABLED, current, from_cache=False,
                                           detail="update checks disabled"))

    if release is None:
        try:
            release = providerlib.build(channel).latest(channel)
        except LifecycleError as error:
            status = OFFLINE if error.code == "UPDATE_CHECK_FAILED" else CHECK_FAILED
            result = _runtime_fields(CheckResult(status, current, detail=error.message,
                                                 checked_at=statelib.now()))
            if record:
                _write_cache(project, result)
            return result

    newer = versionlib.is_newer(release.version, current)
    result = _runtime_fields(CheckResult(UPDATE_AVAILABLE if newer else UP_TO_DATE, current,
                                         latest=release.version, notes=release.notes,
                                         checked_at=statelib.now()))
    if record:
        _write_cache(project, result)
    return result


def cached_notice(project: Path, *, allow_network: bool = False,
                  current: str | None = None) -> dict | None:
    """What a status line may print. Reads the cache; never dials out by itself.

    `current` lets a caller that already loaded the install state pass the
    project's own version, so a cache that predates an update cannot announce
    an update that already happened (#131). Without it, the state is read
    defensively: a corrupt state must not turn a status line into a crash.
    """

    if allow_network:
        return check(project).to_record()
    cached = _read_cache(project)
    if cached is None:
        return None
    if current is None:
        current = _current_without_raising(project, cached)
    return _reconcile_cached(cached, current).to_record()


def notice_line(record: dict | None) -> str:
    """One line a status or doctor output prints for an update record.

    Single owner on purpose: two renderings of the same record drifted the
    first time - `status` printed a raw status where `check` printed a
    sentence - and this line is where the runtime-requirement is surfaced to
    a user whose CLI cannot apply the release it sees.
    """

    if not record:
        return "unknown"
    status = record.get("status")
    latest = record.get("latest")
    if status == UPDATE_AVAILABLE and latest:
        if record.get("runtime_ready", True):
            return f"{latest} available"
        return (f"{latest} available (CLI upgrade required first: "
                f"{upgrade_command(str(latest))})")
    return str(status or "unknown").lower()


def _current_without_raising(project: Path, cached: dict) -> str:
    try:
        state = statelib.load(project)
    except LifecycleError:
        state = None
    if state is not None and state.stack_version:
        return state.stack_version
    fallback = cached.get("current")
    return fallback if isinstance(fallback, str) and fallback else "0.0.0"


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
    # Where each new version landed. Usually `<path>.new`, but never on top
    # of one the user already had (EMP-LC-037).
    side_by_side: list[str] = field(default_factory=list)
    transaction: str | None = None
    rollback_available: bool = False

    def to_record(self) -> dict:
        return {"operation": "update", "applied": self.applied, "dry_run": self.dry_run,
                "from_version": self.from_version, "to_version": self.to_version,
                "check": self.check.to_record(), "plan": self.plan,
                "conflicts": sorted(self.conflicts),
                "side_by_side": sorted(self.side_by_side),
                "transaction": self.transaction,
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


ROLLBACK_SCOPE = ("project assets only - this cannot restore a Python package "
                  "installed elsewhere on the machine")


def rollback_candidate(project: Path):
    """The most recent committed update that can still be reversed.

    Derived from the transaction journal rather than from a second file beside
    it. A separate record had to be written after the transaction committed,
    which left a window where an update had been applied and could no longer be
    rolled back (EMP-LC-017). The journal already knows everything that record
    held, and `undo` marks it ROLLED_BACK, so a reversal cannot run twice.
    """

    from . import transaction as txnlib

    candidates = [item for item in txnlib.read_journals(project)
                  if item.operation == "update" and item.state == txnlib.COMMITTED
                  and item.state_backed_up and item.backup_location
                  and (project / item.backup_location).is_dir()]
    return max(candidates, key=lambda item: item.started_at, default=None)


def _require_matching_runtime(release: providerlib.Release) -> None:
    """Refuse a target this lifecycle runtime does not know (AUD-202).

    The runtime and the target must be the same version - not a compatibility
    matrix, an exact equality. The older runtime's manifests, planner and
    transaction code are what would execute, and nothing inside that runtime
    can prove they implement the policy the target release intends. The
    refusal happens before the archive is fetched and before the first write:
    it costs one bounded metadata request.
    """

    runtime = runtime_version()
    if runtime == release.version:
        return
    direction = "older" if versionlib.is_newer(release.version, runtime) else "different"
    raise LifecycleError(
        "CLI_UPDATE_REQUIRED",
        f"AI Native CLI runtime: {runtime}\n"
        f"Target stack release: {release.version}\n\n"
        f"This project cannot be updated safely with a {direction} lifecycle runtime.\n\n"
        "Upgrade the CLI first:\n"
        f"  {upgrade_command(release.version)}\n\n"
        "Then run:\n"
        "  ainative update",
        runtime_version=runtime, target_version=release.version,
        upgrade_command=upgrade_command(release.version))


def apply(project: Path, *, dry_run: bool = False, force: bool = False,
          distribution: manifestlib.Distribution | None = None) -> UpdateResult:
    """resolve -> runtime gate -> check -> fetch -> verify -> apply -> commit.

    The gate order is load-bearing: the release is resolved (metadata only),
    the runtime contract is checked, and only then is the archive downloaded.
    Everything that can refuse happens before the first project write, so a
    refused update leaves the project byte-identical.
    """

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    state = statelib.load(project)
    if state is None:
        raise LifecycleError("NOT_INSTALLED",
                             f"no AI Native installation recorded in {project}")

    channel = state.update_preferences.get("channel", "stable") or "stable"
    provider = providerlib.build(channel)
    try:
        release = provider.latest(channel)
    except LifecycleError as error:
        # An unreachable or empty source degrades gracefully, exactly as
        # `check` reports it. A source that answered with something this stack
        # refuses (mismatched bundle version, missing digest) is not degraded
        # connectivity - it is a refusal, and it propagates.
        if force or error.code not in ("UPDATE_CHECK_FAILED", "UPDATE_UNAVAILABLE"):
            raise
        outcome = _runtime_fields(CheckResult(
            OFFLINE if error.code == "UPDATE_CHECK_FAILED" else CHECK_FAILED,
            state.stack_version, detail=error.message, checked_at=statelib.now()))
        if not dry_run:
            _write_cache(project, outcome)
        return UpdateResult(False, dry_run, state.stack_version, None, outcome)

    # Availability first, runtime contract second: a project already at the
    # newest release has nothing to apply, so a runtime that differs is not
    # asked to apply anything and gets the truthful "nothing to do" instead of
    # a refusal about work nobody requested.
    applying = force or versionlib.is_newer(release.version, state.stack_version)
    if applying:
        _require_matching_runtime(release)

    # `record=False`: every refusal below this line must leave the project
    # byte-identical, cache included. The cache is refreshed by
    # `ainative update check`, and corrected at read time (#131) - an attempt
    # that did not apply anything writes nothing.
    outcome = check(project, force=True, record=False, state=state, release=release)
    if not applying:
        return UpdateResult(applied=False, dry_run=dry_run, from_version=state.stack_version,
                            to_version=outcome.latest, check=outcome)

    payload = provider.fetch(release)
    providerlib.verify_archive(payload, release.digest)

    staging = Path(tempfile.mkdtemp(prefix="ainative-update-",
                                    dir=str(_staging_root(project))))
    try:
        root = _distribution_root(_safe_extract(payload, staging))
        staged_source = DistributionSource(root=root.resolve(), origin="update",
                                           version=sourcelib.read_version(root))
        # The release named a version; the bytes name another one. SHA-256
        # covers integrity, not identity - this comparison is what makes the
        # filename version and the internal VERSION one fact (AUD-201).
        if staged_source.version != release.version:
            raise LifecycleError(
                "UPDATE_VERSION_MISMATCH",
                f"release {release.version} published a bundle whose internal "
                f"VERSION is {staged_source.version!r}; refusing before any write",
                release_version=release.version, bundle_version=staged_source.version)
        plan, _, _ = installerlib.plan_profile(project, distribution, staged_source,
                                               state.active_profile, operation="update",
                                               state=state)
        conflicts = [change.path for change in plan.changes
                     if change.action == plannerlib.CONFLICT]

        # Before the writes, not after: a `.new` file is a write, and a dry run
        # that produced one was a dry run that changed the project (EMP-LC-024).
        if dry_run:
            return UpdateResult(False, True, state.stack_version, staged_source.version,
                                outcome, plan.to_record(), conflicts)

        result = installerlib.install(project, state.active_profile, operation="update",
                                      distribution=distribution, source=staged_source)
        # After the transaction, not before: a `.new` written first survived an
        # install that then failed, leaving a file no journal knew about and no
        # rollback would remove (EMP-LC-035).
        # `conflicts` stays the files the user changed; `side_by_side` is where
        # each new version actually landed, which is not always `<path>.new`.
        side_by_side = [name for name in
                        (_write_side_by_side(project, plan, staged_source, path,
                                             staged_source.version)
                         for path in conflicts) if name]
        return UpdateResult(True, False, state.stack_version, staged_source.version, outcome,
                            result.plan.to_record(), conflicts, side_by_side,
                            result.transaction,
                            rollback_available=rollback_candidate(project) is not None)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _staging_root(project: Path) -> Path:
    root = project / STAGED_RELATIVE
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_side_by_side(project: Path, plan, source: DistributionSource,
                        path: str, version: str) -> str | None:
    """A file the user changed keeps its content; the new one lands beside it.

    Never on top of an existing `.new`. The stack does not track those files —
    they are the user's to compare and delete — so overwriting one destroyed
    content nothing could restore (EMP-LC-037). A taken name gets the release
    appended, and the path actually used is returned so the caller can report
    it rather than guess.

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
            return None
        for candidate in _side_by_side_names(path, version):
            target = project / candidate
            if not target.exists():
                statelib.write_bytes_atomic(target, payload)
                return candidate
        return None
    return None


def _side_by_side_names(path: str, version: str):
    """`<path>.new`, then names that cannot collide with it."""

    yield f"{path}.new"
    yield f"{path}.new-{version}"
    for index in range(2, 100):
        yield f"{path}.new-{version}-{index}"


def rollback(project: Path, *, dry_run: bool = False) -> dict:
    """Undo the last update from its transaction backup.

    Scope is stated rather than implied: this restores the project's installed
    assets. It cannot restore a Python package installed elsewhere on the
    machine, and it does not claim to.
    """

    from . import transaction as txnlib

    project = installerlib.require_project(project)
    journal = rollback_candidate(project)
    if journal is None:
        raise LifecycleError(
            "ROLLBACK_UNAVAILABLE",
            "no reversible update found for this project: either none has been "
            "applied, the last one was already rolled back, or its backup has "
            "been pruned")
    identifier = journal.identifier
    previous = _backed_up_version(project, journal)

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
                "transaction": identifier, "to_version": previous,
                "would_restore": would_restore, "would_remove": would_remove,
                "scope": ROLLBACK_SCOPE}

    from . import lock as locklib

    with locklib.acquire(project, "update-rollback"):
        outcome = txnlib.undo(project, journal)
    return {"operation": "update rollback", "dry_run": False, "transaction": identifier,
            "to_version": previous, "restored": outcome["restored"],
            "removed": outcome["removed"],
            "install_state_restored": outcome["install_state_restored"],
            "scope": ROLLBACK_SCOPE}


def _backed_up_version(project: Path, journal) -> str | None:
    """The stack version the saved install state carried, if it can be read."""

    if not journal.backup_location:
        return None
    saved = project / journal.backup_location / statelib.STATE_RELATIVE
    try:
        return str(json.loads(saved.read_text(encoding="utf-8")).get("stack_version"))
    except (OSError, ValueError):
        return None


__all__ = [
    "UP_TO_DATE", "UPDATE_AVAILABLE", "OFFLINE", "CHECK_FAILED", "DISABLED", "DISABLE_ENV",
    "CheckResult", "check", "cached_notice", "checks_disabled", "notice_line",
    "runtime_version", "upgrade_command",
    "UpdateResult", "apply", "rollback", "rollback_candidate", "cache_path",
    "ROLLBACK_SCOPE",
    "MAX_EXPANDED_BYTES", "MAX_ARCHIVE_ENTRIES",
]
