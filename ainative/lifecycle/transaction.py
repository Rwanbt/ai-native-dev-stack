"""Apply a plan as a transaction: back up, write, verify, then commit the state.

The guarantee is stated in ADR-0009 §4 and enforced here: an interruption at any
point leaves the project in the old valid state or the new one, never between.
Two mechanisms produce it.

*Backups.* Every file the plan will overwrite or delete is copied into a
transaction-scoped backup directory **before** the first write. Rollback is a
copy back, not a reconstruction.

*Commit last.* The install state is written only after every file change has
been applied and re-read. Until that write lands, the on-disk state still
describes the previous install — so a crash is a rollback that has not run yet,
and `repair` runs it from the journal.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from . import digest as digestlib
from . import external
from . import manifest as manifestlib
from . import planner as plannerlib
from . import state as statelib
from .errors import LifecycleError
from .manifest import Component, Distribution
from .paths import is_within, resolve_within, validate_relative
from .planner import Change, Plan
from .source import DistributionSource

PREPARED = "PREPARED"
APPLYING = "APPLYING"
COMMITTED = "COMMITTED"
ROLLED_BACK = "ROLLED_BACK"
INTERRUPTED = "INTERRUPTED"

# Keep the last N transaction journals and their backups. Unbounded growth in a
# hidden directory is a slow disk leak nobody notices until it matters.
RETENTION = 5

# What this code writes as an id, and therefore the only shape it will read
# back. A journal is data inside the project; its id becomes a filename.
_JOURNAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass
class Journal:
    identifier: str
    operation: str
    from_profile: str | None
    to_profile: str | None
    state: str = PREPARED
    planned_changes: list[dict] = field(default_factory=list)
    completed_changes: list[dict] = field(default_factory=list)
    backup_location: str | None = None
    started_at: str = field(default_factory=statelib.now)
    finished_at: str | None = None
    stack_version: str = "0.0.0"
    # Whether the install state this transaction was about to replace was saved
    # alongside the files. Without it an undo restores the bytes and leaves the
    # record describing a version that is no longer on disk (EMP-LC-014).
    state_backed_up: bool = False

    def to_record(self) -> dict:
        return {
            "schema_version": 1,
            "id": self.identifier,
            "operation": self.operation,
            "from_profile": self.from_profile,
            "to_profile": self.to_profile,
            "state": self.state,
            "planned_changes": self.planned_changes,
            "completed_changes": self.completed_changes,
            "backup_location": self.backup_location,
            "state_backed_up": self.state_backed_up,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stack_version": self.stack_version,
        }

    @classmethod
    def from_record(cls, raw: dict) -> "Journal":
        # A journal file sits inside the project, so anything that can write to
        # the project can write one. Its id becomes a filename and its
        # `backup_location` becomes a directory we read and write, so both are
        # validated here rather than trusted: an id of `../../../escaped` made
        # `repair` write outside the project root (EMP-LC-019).
        identifier = str(raw.get("id", ""))
        if not _JOURNAL_ID.match(identifier):
            raise LifecycleError("INSTALL_STATE_CORRUPTED",
                                 f"transaction journal has an illegal id: {identifier!r}")
        location = raw.get("backup_location")
        if location is not None:
            if not isinstance(location, str):
                raise LifecycleError("INSTALL_STATE_CORRUPTED",
                                     "transaction journal has a non-string backup_location")
            validate_relative(location)      # refuses .., absolute, drive, UNC, NUL
        return cls(
            identifier=identifier,
            operation=str(raw.get("operation", "")),
            from_profile=raw.get("from_profile"),
            to_profile=raw.get("to_profile"),
            state=str(raw.get("state", PREPARED)),
            planned_changes=list(raw.get("planned_changes", [])),
            completed_changes=list(raw.get("completed_changes", [])),
            backup_location=raw.get("backup_location"),
            started_at=str(raw.get("started_at", "")),
            finished_at=raw.get("finished_at"),
            stack_version=str(raw.get("stack_version", "0.0.0")),
            state_backed_up=bool(raw.get("state_backed_up", False)),
        )

    @property
    def effective_state(self) -> str:
        """`APPLYING` on disk means the process never reached commit."""

        return INTERRUPTED if self.state == APPLYING else self.state


def transactions_dir(project: Path) -> Path:
    return project / statelib.TRANSACTIONS_RELATIVE


def backups_dir(project: Path) -> Path:
    return project / statelib.BACKUPS_RELATIVE


def journal_path(project: Path, identifier: str) -> Path:
    return transactions_dir(project) / f"{identifier}.json"


def write_journal(project: Path, journal: Journal) -> Path:
    if not _JOURNAL_ID.match(journal.identifier):
        raise LifecycleError("INSTALL_STATE_CORRUPTED",
                             f"refusing to write a journal with id {journal.identifier!r}")
    path = journal_path(project, journal.identifier)
    statelib.write_atomic(path, json.dumps(journal.to_record(), indent=2, sort_keys=True) + "\n")
    return path


def read_journals(project: Path) -> list[Journal]:
    directory = transactions_dir(project)
    if not directory.is_dir():
        return []
    journals: list[Journal] = []
    for path in sorted(directory.glob("*.json")):
        try:
            journals.append(Journal.from_record(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, LifecycleError):
            # Unreadable or illegal: it is not a transaction this code wrote, so
            # it governs nothing. `malformed(project)` reports it to `doctor`;
            # the file itself is left alone because it may be evidence.
            continue
    return journals


def malformed(project: Path) -> list[str]:
    """Journal files this code refuses to read, for `doctor` to report."""

    directory = transactions_dir(project)
    if not directory.is_dir():
        return []
    rejected: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            Journal.from_record(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, LifecycleError):
            rejected.append(path.name)
    return rejected


def interrupted(project: Path) -> list[Journal]:
    return [item for item in read_journals(project) if item.effective_state == INTERRUPTED]


def prune(project: Path, keep: int = RETENTION) -> None:
    """Drop the oldest journals and their backups, newest `keep` retained."""

    journals = sorted(read_journals(project), key=lambda item: item.started_at)
    for journal in journals[:-keep] if len(journals) > keep else []:
        if journal.effective_state == INTERRUPTED:
            continue  # never discard evidence a repair still needs
        journal_path(project, journal.identifier).unlink(missing_ok=True)
        location = backups_dir(project) / journal.identifier
        if location.is_dir() and is_within(project, location):
            shutil.rmtree(location, ignore_errors=True)


# --- the applier ---------------------------------------------------------


class Applier:
    """Executes one plan under one journal. Never used twice."""

    def __init__(self, project: Path, distribution: Distribution,
                 source: DistributionSource | None, plan: Plan) -> None:
        self.project = project.resolve()
        self.distribution = distribution
        self.source = source
        self.plan = plan
        self.journal = Journal(
            identifier=statelib.new_identifier("txn"),
            operation=plan.operation,
            from_profile=plan.from_profile,
            to_profile=plan.to_profile,
            planned_changes=[change.to_record() for change in plan.mutating],
            stack_version=source.version if source else "0.0.0",
        )
        self.backup_root = backups_dir(self.project) / self.journal.identifier
        self.applied: list[tuple[Change, Path]] = []

    # --- backup ---------------------------------------------------------

    def _backup(self, change: Change, target: Path) -> None:
        """Copy what is about to be replaced or deleted, file or whole tree.

        A `data_root` change names a directory, and `--purge` deletes it. A
        file-only backup made that deletion unrecoverable (EMP-LC-006).
        """

        if not target.exists() or target.is_symlink():
            return
        destination = self.backup_root / change.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            if self._contains_backup_root(target):
                # Copying a directory that holds the backup root into a
                # subdirectory of itself recurses forever (EMP-LC-010). Such a
                # path must be handled outside the transaction, not backed up.
                raise LifecycleError(
                    "APPLY_FAILED",
                    f"refusing to back up {change.path}: it contains this "
                    "transaction's own backup directory")
            shutil.copytree(target, destination, dirs_exist_ok=True, symlinks=True)
            return
        shutil.copy2(target, destination)

    def _contains_backup_root(self, directory: Path) -> bool:
        try:
            self.backup_root.resolve(strict=False).relative_to(directory.resolve(strict=False))
        except ValueError:
            return False
        return True

    def _restore(self, change: Change, target: Path) -> None:
        saved = self.backup_root / change.path
        if saved.is_dir():
            shutil.copytree(saved, target, dirs_exist_ok=True, symlinks=True)
        elif saved.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, target)
        elif target.exists() and change.action in (plannerlib.CREATE,):
            target.unlink(missing_ok=True)

    # --- individual actions ---------------------------------------------

    def _write_file(self, change: Change, target: Path) -> None:
        component = self.distribution.component(change.component)
        if component.kind == manifestlib.KIND_MARKER:
            if self.source is None:
                raise LifecycleError("APPLY_FAILED",
                                     f"no distribution source to write {change.path}")
            payload = plannerlib.marker_payload(
                component, self.source, self.plan.to_profile or "standard").encode("utf-8")
        else:
            if self.source is None or change.source is None:
                raise LifecycleError("APPLY_FAILED",
                                     f"no distribution source to install {change.path}")
            payload = self.source.path(change.source).read_bytes()
        statelib.write_bytes_atomic(target, payload)
        self._make_executable_if_declared(component, change, target)

    @staticmethod
    def _make_executable_if_declared(component: Component, change: Change, target: Path) -> None:
        if os.name == "nt" or not component.executable:
            return
        if Path(change.path).name in component.executable:
            target.chmod(target.stat().st_mode | 0o111)

    def _remove_path(self, change: Change, target: Path) -> None:
        """Delete one owned path, never following a link out of the project."""

        if not is_within(self.project, target):
            raise LifecycleError("PATH_ESCAPE",
                                 f"refused to remove {change.path}: outside the project root")
        if target.is_symlink():
            target.unlink(missing_ok=True)
            return
        if target.is_dir():
            shutil.rmtree(target)
            return
        target.unlink(missing_ok=True)
        self._prune_empty_parents(target.parent)

    def _prune_empty_parents(self, directory: Path) -> None:
        current = directory
        while is_within(self.project, current) and current != self.project:
            try:
                next(current.iterdir())
                return
            except StopIteration:
                current.rmdir()
                current = current.parent
            except OSError:
                return

    def _apply_block(self, change: Change, target: Path, *, remove: bool) -> None:
        component = self.distribution.component(change.component)
        spec = plannerlib.block_spec(component)
        if remove:
            content, changed = external.remove(target, spec)
            if not changed:
                return
            if content is None:
                target.unlink(missing_ok=True)
                return
            statelib.write_atomic(target, content)
            return
        content, changed = external.apply(target, spec)
        if changed:
            statelib.write_atomic(target, content)

    def _apply(self, change: Change) -> None:
        target = resolve_within(self.project, change.path)
        self._backup(change, target)
        if change.action in (plannerlib.CREATE, plannerlib.REPLACE):
            self._write_file(change, target)
        elif change.action == plannerlib.REMOVE:
            self._remove_path(change, target)
        elif change.action == plannerlib.BLOCK_WRITE:
            self._apply_block(change, target, remove=False)
        elif change.action == plannerlib.BLOCK_REMOVE:
            self._apply_block(change, target, remove=True)
        else:
            return
        self.applied.append((change, target))
        self.journal.completed_changes.append(change.to_record())

    # --- verification ----------------------------------------------------

    def _verify(self) -> None:
        """Re-read what was written. A write that did not land is a failure."""

        for change, target in self.applied:
            if change.action in (plannerlib.CREATE, plannerlib.REPLACE):
                if change.digest and digestlib.digest_file(target) != change.digest:
                    raise LifecycleError("APPLY_FAILED",
                                         f"{change.path} does not hold the expected content "
                                         "after being written")
            elif change.action == plannerlib.REMOVE and target.exists():
                raise LifecycleError("APPLY_FAILED", f"{change.path} still exists after removal")

    def _backup_install_state(self) -> None:
        """Save the install state this transaction is about to replace.

        Undoing a committed transaction has to put the record back as well as
        the bytes. Without this, `update rollback` restored v1's files and left
        a state that still described v2 (EMP-LC-014).
        """

        current = statelib.state_path(self.project)
        if not current.is_file():
            return
        destination = self.backup_root / statelib.STATE_RELATIVE
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, destination)
        self.journal.state_backed_up = True

    def rollback(self) -> None:
        for change, target in reversed(self.applied):
            try:
                self._restore(change, target)
            except OSError:
                continue
        restore_install_state(self.project, self.journal)
        self.journal.state = ROLLED_BACK
        self.journal.finished_at = statelib.now()
        write_journal(self.project, self.journal)

    # --- entry point -----------------------------------------------------

    def run(self, commit: Callable[[], None]) -> Journal:
        """Apply every mutating change, verify, then let the caller commit state."""

        write_journal(self.project, self.journal)
        self.journal.state = APPLYING
        self.journal.backup_location = str(
            self.backup_root.relative_to(self.project).as_posix())
        self._backup_install_state()
        write_journal(self.project, self.journal)

        try:
            for change in self.plan.mutating:
                self._apply(change)
            self._verify()
            commit()   # the install state is written here, and only here
        except BaseException:
            self.rollback()
            raise

        self.journal.state = COMMITTED
        self.journal.finished_at = statelib.now()
        write_journal(self.project, self.journal)
        prune(self.project)
        return self.journal


def restore_install_state(project: Path, journal: Journal) -> bool:
    """Put back the install state this transaction replaced, if it saved one."""

    if not journal.state_backed_up or not journal.backup_location:
        return False
    saved = project / journal.backup_location / statelib.STATE_RELATIVE
    if not saved.is_file():
        return False
    statelib.write_atomic(statelib.state_path(project),
                          saved.read_text(encoding="utf-8"))
    return True


def undo(project: Path, journal: Journal) -> dict:
    """Reverse one transaction's completed changes, files and state alike.

    Deterministic and conservative: it restores every path the journal recorded
    as completed, removes a file that was created and therefore has no backup,
    and puts the install state back. It never guesses at a change that was
    planned but not recorded as completed — that change never ran.
    """

    restored: list[str] = []
    removed: list[str] = []
    backup_root = project / journal.backup_location if journal.backup_location else None
    for record in reversed(journal.completed_changes):
        path = record.get("path")
        if not isinstance(path, str):
            continue
        target = resolve_within(project, path)
        saved = backup_root / path if backup_root else None
        if saved is not None and saved.is_dir():
            shutil.copytree(saved, target, dirs_exist_ok=True, symlinks=True)
            restored.append(path)
        elif saved is not None and saved.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, target)
            restored.append(path)
        elif record.get("action") == plannerlib.CREATE and target.is_file():
            # Created by this transaction, so there is nothing to restore: the
            # previous state did not have it. Leaving it behind is what made
            # `update rollback` produce a v1 project holding v2's new files.
            target.unlink(missing_ok=True)
            removed.append(path)

    state_restored = restore_install_state(project, journal)
    journal.state = ROLLED_BACK
    journal.finished_at = statelib.now()
    write_journal(project, journal)
    return {"transaction": journal.identifier, "action": "rolled_back",
            "restored": sorted(restored), "removed": sorted(removed),
            "install_state_restored": state_restored}


def recover(project: Path, journal: Journal) -> dict:
    """Undo an interrupted transaction. A committed one is not touched here."""

    if journal.effective_state != INTERRUPTED:
        return {"transaction": journal.identifier, "action": "none",
                "state": journal.effective_state}
    return undo(project, journal)


def summarise(journals: Sequence[Journal]) -> list[dict]:
    return [{"id": item.identifier, "operation": item.operation,
             "state": item.effective_state, "started_at": item.started_at}
            for item in journals]


__all__ = [
    "PREPARED", "APPLYING", "COMMITTED", "ROLLED_BACK", "INTERRUPTED", "RETENTION",
    "Journal", "Applier", "recover", "undo", "restore_install_state",
    "read_journals", "malformed", "interrupted", "prune",
    "transactions_dir", "backups_dir", "journal_path", "write_journal", "summarise",
]
