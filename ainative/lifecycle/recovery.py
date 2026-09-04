"""`doctor` diagnoses; `repair` fixes. They are separate on purpose.

A diagnostic that repairs is a diagnostic nobody can run safely on a broken
install to find out what is broken. So `doctor` reads and never writes, and
`repair` acts only on what `doctor` would report.

Neither of them overwrites a `USER_MODIFIED` file. A repair that restores the
shipped version of a file the user edited is a data-loss bug wearing the word
"repair".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import digest as digestlib
from . import legacy as legacylib
from . import lock as locklib
from . import manifest as manifestlib
from . import planner as plannerlib
from . import source as sourcelib
from . import state as statelib
from . import transaction as txnlib
from . import updater as updaterlib
from .errors import LifecycleError
from .external import BlockSpec, count as block_count
from .manifest import Distribution
from .paths import resolve_within

OK = "OK"
MISSING = "MISSING"
USER_MODIFIED = "USER_MODIFIED"
CORRUPTED = "CORRUPTED"
ORPHANED = "ORPHANED"
INTERRUPTED = "INTERRUPTED"
DUPLICATE = "DUPLICATE"


@dataclass
class Diagnosis:
    project: Path
    installed: bool
    active_profile: str | None
    stack_version: str | None
    findings: list[dict] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)
    lock: dict | None = None
    legacy: dict | None = None
    update: dict | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        blocking = {MISSING, CORRUPTED, ORPHANED, INTERRUPTED, DUPLICATE}
        return not any(item["status"] in blocking for item in self.findings) \
            and not self.transactions

    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for item in self.findings:
            tally[item["status"]] = tally.get(item["status"], 0) + 1
        return tally

    def to_record(self) -> dict:
        return {
            "project": str(self.project),
            "installed": self.installed,
            "active_profile": self.active_profile,
            "stack_version": self.stack_version,
            "healthy": self.healthy,
            "counts": self.counts(),
            "findings": self.findings,
            "interrupted_transactions": self.transactions,
            "lock": self.lock,
            "legacy": self.legacy,
            "update": self.update,
            "notes": list(self.notes),
        }


def _file_finding(project: Path, entry: statelib.ManagedFile,
                  distribution: Distribution) -> dict:
    component = distribution.components.get(entry.component)
    target = resolve_within(project, entry.path)

    if component is None:
        return {"path": entry.path, "component": entry.component, "status": ORPHANED,
                "detail": "component is no longer declared by any profile"}

    if entry.kind == "data_root":
        # A data root is declared, never installed. Its absence means the user
        # has not created any of that data yet — reporting MISSING here made a
        # healthy fresh Verified install exit non-zero (EMP-LC-001).
        return {"path": entry.path, "component": entry.component, "status": OK,
                "detail": "user data root (present)" if target.exists()
                else "user data root (none yet)"}

    if entry.kind == "external_block":
        spec = BlockSpec(component.marker or component.identifier,
                         component.comment_prefix, component.lines)
        found = block_count(target, spec)
        if found == 0:
            return {"path": entry.path, "component": entry.component, "status": MISSING,
                    "detail": "managed region absent from the file"}
        if found > 1:
            return {"path": entry.path, "component": entry.component, "status": DUPLICATE,
                    "detail": f"{found} managed regions found; expected one"}
        return {"path": entry.path, "component": entry.component, "status": OK, "detail": ""}

    if entry.ownership == manifestlib.USER_DATA:
        present = target.exists()
        return {"path": entry.path, "component": entry.component,
                "status": OK if present else MISSING,
                "detail": "user-owned copy" if present else "user-owned copy is absent"}

    status = digestlib.classify(target, entry.digest_at_install)
    mapping = {digestlib.UNCHANGED: OK, digestlib.USER_MODIFIED: USER_MODIFIED,
               digestlib.MISSING: MISSING, digestlib.CONFLICT: CORRUPTED}
    detail = {"UNCHANGED": "", "USER_MODIFIED": "edited since install — will not be overwritten",
              "MISSING": "recorded as installed but absent",
              "CONFLICT": "present but its install digest is unknown"}[status]
    return {"path": entry.path, "component": entry.component,
            "status": mapping[status], "detail": detail}


def diagnose(project: Path, *, distribution: Distribution | None = None,
             check_updates: bool = False) -> Diagnosis:
    from . import installer as installerlib

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    try:
        state = statelib.load(project)
        corrupt = None
    except LifecycleError as error:
        state, corrupt = None, error

    diagnosis = Diagnosis(project=project, installed=state is not None,
                          active_profile=state.active_profile if state else None,
                          stack_version=state.stack_version if state else None)

    if corrupt is not None:
        diagnosis.findings.append({"path": statelib.STATE_RELATIVE.as_posix(),
                                   "component": "lifecycle", "status": CORRUPTED,
                                   "detail": corrupt.message})
        return diagnosis

    markers = legacylib.detect(project)
    if markers and state is None:
        diagnosis.legacy = {"legacy_install": True, "markers": list(markers)}
        diagnosis.notes.append(
            "This project holds AI Native files but no lifecycle state. "
            "`ainative init` adopts them without overwriting your edits.")

    if state is not None:
        for entry in sorted(state.managed_files, key=lambda item: item.path):
            diagnosis.findings.append(_file_finding(project, entry, distribution))
        for identifier in state.installed_components:
            if identifier not in distribution.components:
                diagnosis.findings.append({"path": "-", "component": identifier,
                                           "status": ORPHANED,
                                           "detail": "installed component is no longer declared"})
        if state.adopted_from_legacy:
            diagnosis.legacy = {"legacy_install": True, "adopted": True}

    diagnosis.transactions = txnlib.summarise(txnlib.interrupted(project))
    diagnosis.lock = locklib.describe(project)
    diagnosis.update = updaterlib.cached_notice(project, allow_network=check_updates)
    return diagnosis


@dataclass
class RepairResult:
    diagnosis: Diagnosis
    recovered: list[dict] = field(default_factory=list)
    reinstalled: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    dry_run: bool = False
    transaction: str | None = None

    def to_record(self) -> dict:
        return {
            "operation": "repair",
            "dry_run": self.dry_run,
            "recovered_transactions": self.recovered,
            "reinstalled": sorted(self.reinstalled),
            "dropped_records": sorted(self.dropped),
            "preserved_user_modified": sorted(self.preserved),
            "transaction": self.transaction,
            "diagnosis": self.diagnosis.to_record(),
        }


def repair(project: Path, *, dry_run: bool = False,
           distribution: Distribution | None = None,
           source: sourcelib.DistributionSource | None = None,
           force_unlock: bool = False) -> RepairResult:
    """Recover interrupted transactions, then restore what is safely restorable."""

    from . import installer as installerlib

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    diagnosis = diagnose(project, distribution=distribution)
    result = RepairResult(diagnosis=diagnosis, dry_run=dry_run)

    result.preserved = [item["path"] for item in diagnosis.findings
                        if item["status"] == USER_MODIFIED]
    missing = [item["path"] for item in diagnosis.findings if item["status"] == MISSING]
    orphaned = [item["path"] for item in diagnosis.findings if item["status"] == ORPHANED]
    result.reinstalled = missing
    result.dropped = orphaned

    if dry_run:
        result.recovered = [{"transaction": item["id"], "action": "would_roll_back"}
                            for item in diagnosis.transactions]
        return result

    from . import lock as locklib_local

    with locklib_local.acquire(project, "repair", force=force_unlock):
        for journal in txnlib.interrupted(project):
            result.recovered.append(txnlib.recover(project, journal))

        state = statelib.load(project)
        if state is None:
            result.diagnosis = diagnose(project, distribution=distribution)
            return result

        if orphaned:
            for path in orphaned:
                state.managed_files = [item for item in state.managed_files
                                       if item.path != path]
            state.installed_components = [item for item in state.installed_components
                                          if item in distribution.components]
            statelib.save(project, state)

    if missing:
        source = source or sourcelib.resolve()
        outcome = installerlib.install(project, state.active_profile, operation="repair",
                                       distribution=distribution, source=source,
                                       force_unlock=force_unlock)
        result.transaction = outcome.transaction
        result.reinstalled = [change.path for change in outcome.plan.mutating]

    result.diagnosis = diagnose(project, distribution=distribution)
    return result


__all__ = ["OK", "MISSING", "USER_MODIFIED", "CORRUPTED", "ORPHANED", "INTERRUPTED",
           "DUPLICATE", "Diagnosis", "diagnose", "RepairResult", "repair"]
