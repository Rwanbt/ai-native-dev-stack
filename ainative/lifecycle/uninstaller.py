"""Remove the stack from a project without removing the user's work.

Two operations, deliberately far apart:

`uninstall` withdraws the active stack. It removes managed files that still hold
the bytes the stack wrote, takes back its regions in files it does not own, and
leaves everything else — user-modified managed files, user data, Verified
history — exactly where it is.

`uninstall --purge` additionally deletes the data roots the manifests declare as
user data. It never touches a path outside a root AI Native explicitly owns, it
prints those paths first, and without a TTY it requires `--yes`.

`git clean`, `git checkout .` and `git restore .` are prohibited here (ADR-0009
§7). They operate on the user's working tree rather than on what the stack owns.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import manifest as manifestlib
from . import planner as plannerlib
from . import state as statelib
from . import transaction as txnlib
from .errors import LifecycleError
from .manifest import Distribution
from .paths import is_within
from .planner import Plan
from .state import InstallState

# The only roots `--purge` may delete outright, beyond the manifests' declared
# data roots. Everything else must be named by a managed-file record.
PURGE_ROOTS = (".ai-native",)


@dataclass
class UninstallResult:
    plan: Plan
    applied: bool
    dry_run: bool
    purge: bool
    removed: list[str]
    preserved_user_modified: list[str]
    preserved_user_data: list[str]
    transaction: str | None = None

    def summary(self) -> dict:
        return {"removed": len(self.removed),
                "preserved_user_modified": len(self.preserved_user_modified),
                "preserved_user_data": len(self.preserved_user_data)}

    def to_record(self) -> dict:
        return {
            "operation": "uninstall-purge" if self.purge else "uninstall",
            "applied": self.applied,
            "dry_run": self.dry_run,
            "summary": self.summary(),
            "removed": sorted(self.removed),
            "preserved_user_modified": sorted(self.preserved_user_modified),
            "preserved_user_data": sorted(self.preserved_user_data),
            "plan": self.plan.to_record(),
            "transaction": self.transaction,
        }


def _classify_plan(plan: Plan, state: InstallState) -> tuple[list[str], list[str], list[str]]:
    # A block removal takes back a region, not the file. Reporting both as
    # "removed" told a user their .gitignore would be deleted (EMP-LC-002).
    removed = [c.path for c in plan.changes if c.action == plannerlib.REMOVE]
    removed += [f"{c.path} (managed region only)" for c in plan.changes
                if c.action == plannerlib.BLOCK_REMOVE]
    user_data = [c.path for c in plan.changes
                 if c.action == plannerlib.PRESERVE
                 and c.ownership in (manifestlib.USER_DATA,)]
    user_modified = [c.path for c in plan.changes
                     if c.action == plannerlib.PRESERVE
                     and c.ownership not in (manifestlib.USER_DATA,)]
    return removed, user_modified, user_data


def _remove_lifecycle_bookkeeping(project: Path) -> list[str]:
    """Delete the lifecycle's own directory — after the transaction, never inside it.

    This cannot be a change in the plan. The journal and the backups live under
    `.ai-native/lifecycle/`, so backing that directory up copies it into itself
    and recurses until the interpreter gives up (EMP-LC-010). By the time this
    runs the transaction has committed, and a purge is exactly the operation
    that gives up the ability to roll it back.
    """

    removed: list[str] = []
    root = project / statelib.LIFECYCLE_DIRNAME
    if not is_within(project, root) or not root.is_dir():
        return removed

    # Named, not `rmtree`. Emptying the directory took anything a user had put
    # there with it (EMP-LC-020); these are the paths the lifecycle itself
    # writes, and nothing else is ours to delete.
    for relative in (statelib.STATE_RELATIVE, statelib.UPDATE_CACHE_RELATIVE,
                     statelib.TRANSACTIONS_RELATIVE, statelib.BACKUPS_RELATIVE,
                     statelib.LIFECYCLE_DIRNAME / "staged"):
        target = project / relative
        if not target.exists() or not is_within(project, target):
            continue
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        removed.append(relative.as_posix())

    try:
        next(root.iterdir())
    except StopIteration:
        root.rmdir()
        removed.append(statelib.LIFECYCLE_DIRNAME.as_posix())
    except OSError:
        pass
    # `.ai-native/` itself belongs to us; remove it only once it is empty, so a
    # directory somebody else put something in survives.
    parent = root.parent
    if parent.is_dir() and parent != project and is_within(project, parent):
        try:
            next(parent.iterdir())
        except StopIteration:
            parent.rmdir()
            removed.append(parent.relative_to(project).as_posix())
        except OSError:
            pass
    return removed


def plan_uninstall(project: Path, distribution: Distribution, state: InstallState, *,
                   purge: bool) -> Plan:
    plan = plannerlib.build_uninstall_plan(project, distribution, state, purge=purge)
    if purge:
        plan.notes.append("--purge also removes .ai-native/lifecycle/ (state, journal, "
                          "backups, update cache) once the transaction has committed; "
                          "rollback is not possible afterwards")
    return plan


def uninstall(project: Path, *, purge: bool = False, dry_run: bool = False,
              assume_yes: bool = False, interactive: bool = False,
              distribution: Distribution | None = None,
              force_unlock: bool = False) -> UninstallResult:
    from . import installer as installerlib
    from . import lock as locklib

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    state = statelib.load(project)
    if state is None:
        raise LifecycleError("NOT_INSTALLED",
                             f"no AI Native installation recorded in {project}")

    plan = plan_uninstall(project, distribution, state, purge=purge)
    removed, user_modified, user_data = _classify_plan(plan, state)

    if dry_run:
        if purge:
            removed = removed + [statelib.LIFECYCLE_DIRNAME.as_posix()]
        return UninstallResult(plan, applied=False, dry_run=True, purge=purge,
                               removed=removed, preserved_user_modified=user_modified,
                               preserved_user_data=user_data)

    if purge and not assume_yes and not interactive:
        raise LifecycleError(
            "CONFIRMATION_REQUIRED",
            "--purge deletes the paths listed in the plan, including Verified history. "
            "Re-run with --yes to confirm, or --dry-run to review it first.",
            paths=sorted(removed))

    pending = txnlib.interrupted(project)
    if pending:
        raise LifecycleError("TRANSACTION_IN_PROGRESS",
                             "an interrupted transaction must be repaired first: "
                             "run `ainative repair`.",
                             transactions=txnlib.summarise(pending))

    with locklib.acquire(project, "uninstall", force=force_unlock):
        state = statelib.load(project) or state
        plan = plan_uninstall(project, distribution, state, purge=purge)
        removed, user_modified, user_data = _classify_plan(plan, state)
        applier = txnlib.Applier(project, distribution, None, plan)
        journal = applier.run(lambda: _commit(project, state, plan, purge))

    # After the lock is released, not inside it: the lock file lives in the very
    # directory this removes, so from inside the block it is never empty and the
    # purge left a hollow `.ai-native/lifecycle/` behind. By here the state is
    # already gone, so a concurrent operation sees an uninstalled project.
    if purge:
        removed += _remove_lifecycle_bookkeeping(project)

    return UninstallResult(plan, applied=True, dry_run=False, purge=purge, removed=removed,
                           preserved_user_modified=user_modified,
                           preserved_user_data=user_data,
                           transaction=journal.identifier)


def _commit(project: Path, state: InstallState, plan: Plan, purge: bool) -> None:
    """After a default uninstall the state must still describe what survived."""

    if purge:
        statelib.remove(project)
        return
    survivors = []
    for entry in state.managed_files:
        if any(change.path == entry.path
               and change.action in (plannerlib.REMOVE, plannerlib.BLOCK_REMOVE)
               for change in plan.changes):
            continue
        survivors.append(entry)
    state.managed_files = survivors
    state.installed_components = []
    state.previous_profile = state.active_profile
    state.last_transaction = None
    statelib.save(project, state)


def purge_profile(project: Path, profile_name: str, *, dry_run: bool = False,
                  assume_yes: bool = False, interactive: bool = False,
                  distribution: Distribution | None = None,
                  force_unlock: bool = False) -> UninstallResult:
    """Delete one profile's user data. Never implied by `profile switch`."""

    from . import installer as installerlib
    from . import lock as locklib

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    distribution.profile(profile_name)
    state = statelib.load(project)
    if state is None:
        raise LifecycleError("NOT_INSTALLED",
                             f"no AI Native installation recorded in {project}")

    # The same gate every other mutation passes. Purge is the most destructive
    # operation there is, and it was the one running on a project whose last
    # transaction never finished (EMP-LC-016).
    pending = txnlib.interrupted(project)
    if pending and not dry_run:
        raise LifecycleError("TRANSACTION_IN_PROGRESS",
                             "an interrupted transaction must be repaired before data "
                             "can be purged: run `ainative repair`.",
                             transactions=txnlib.summarise(pending))

    own = set(distribution.profile(profile_name).components)
    plan = Plan(operation=f"profile-purge-{profile_name}", project=project,
                from_profile=state.active_profile, to_profile=state.active_profile)
    for identifier in sorted(own):
        component = distribution.components.get(identifier)
        if component is None or component.ownership != manifestlib.USER_DATA:
            continue
        for path in component.paths:
            if (project / path).exists():
                plan.changes.append(plannerlib.Change(
                    plannerlib.REMOVE, path, identifier, component.ownership,
                    f"explicit purge of {profile_name} data", kind="data_root"))
        plan.components_removed.append(identifier)

    removed = [change.path for change in plan.changes if change.action == plannerlib.REMOVE]
    if dry_run:
        return UninstallResult(plan, applied=False, dry_run=True, purge=True,
                               removed=removed, preserved_user_modified=[],
                               preserved_user_data=[])
    if not removed:
        return UninstallResult(plan, applied=False, dry_run=False, purge=True, removed=[],
                               preserved_user_modified=[], preserved_user_data=[])
    if not assume_yes and not interactive:
        raise LifecycleError(
            "CONFIRMATION_REQUIRED",
            f"purging {profile_name} data permanently deletes: " + ", ".join(sorted(removed))
            + ". Re-run with --yes to confirm.", paths=sorted(removed))

    with locklib.acquire(project, "profile-purge", force=force_unlock):
        applier = txnlib.Applier(project, distribution, None, plan)
        journal = applier.run(lambda: _commit_purge(project, state, plan))
    return UninstallResult(plan, applied=True, dry_run=False, purge=True, removed=removed,
                           preserved_user_modified=[], preserved_user_data=[],
                           transaction=journal.identifier)


def _commit_purge(project: Path, state: InstallState, plan: Plan) -> None:
    purged = {change.path for change in plan.changes if change.action == plannerlib.REMOVE}
    state.managed_files = [item for item in state.managed_files if item.path not in purged]
    for identifier in plan.components_removed:
        state.drop_component(identifier)
    statelib.save(project, state)


__all__ = ["UninstallResult", "uninstall", "purge_profile", "plan_uninstall", "PURGE_ROOTS"]
