"""Install a profile, and move between profiles.

`init` and `profile switch` are the same operation with a different starting
point, so they share one code path: resolve the target profile, plan the delta,
and apply it under a transaction. Nothing reinstalls what is already current —
the plan is built from the recorded digests, so a second `init standard` is a
no-op by construction rather than by a special case.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import legacy as legacylib
from . import manifest as manifestlib
from . import planner as plannerlib
from . import source as sourcelib
from . import state as statelib
from . import transaction as txnlib
from .errors import LifecycleError
from .manifest import Distribution
from .planner import Plan
from .source import DistributionSource
from .state import InstallState

# Where the Verified trust anchor lives, mirrored from
# ainative_workplane.bootstrap.TRUST_RELATIVE. Mirrored rather than imported so
# the Standard profile never loads an authority module to install itself
# (ADR-0009 §1). The Verified suite asserts the two stay equal.
TRUST_ANCHOR_RELATIVE = ".ai-native/trust/project_trust.json"

VERIFIED_BOOTSTRAP_NOTICE = (
    "Verified is active, but this project has no trust anchor yet. Trust "
    "bootstrap is a privileged human act: the Work Plane cannot verify who "
    "performed it, so the installer will not perform it for you (ADR-0006).\n"
    "  ainative trust bootstrap --repo . --approval-root <file> "
    "--policy <file> --by \"<you>\" --signer <fingerprint>"
)


@dataclass
class OperationResult:
    operation: str
    plan: Plan
    applied: bool
    dry_run: bool
    state: InstallState | None
    transaction: str | None = None
    notices: list[str] = None  # type: ignore[assignment]
    legacy: legacylib.Adoption | None = None

    def __post_init__(self) -> None:
        if self.notices is None:
            self.notices = []

    def to_record(self) -> dict:
        record = {
            "operation": self.operation,
            "applied": self.applied,
            "dry_run": self.dry_run,
            "plan": self.plan.to_record(),
            "transaction": self.transaction,
            "notices": list(self.notices),
            "active_profile": self.state.active_profile if self.state else None,
        }
        if self.legacy is not None and self.legacy.detected:
            record["legacy_adoption"] = self.legacy.to_record()
        return record


def require_project(project: Path) -> Path:
    resolved = Path(project).expanduser().resolve()
    if not resolved.is_dir():
        raise LifecycleError("PROJECT_ROOT_INVALID", f"{resolved} is not a directory")
    return resolved


def trust_anchor_present(project: Path) -> bool:
    """A file test, deliberately: reading the anchor is the Work Plane's job."""

    return (project / TRUST_ANCHOR_RELATIVE).is_file()


def _blocking_transaction(project: Path) -> None:
    pending = txnlib.interrupted(project)
    if pending:
        raise LifecycleError(
            "TRANSACTION_IN_PROGRESS",
            f"{len(pending)} interrupted transaction(s) must be repaired first: "
            "run `ainative repair`.",
            transactions=txnlib.summarise(pending))


def _fresh_state(source: DistributionSource, profile: str) -> InstallState:
    return InstallState(stack_version=source.version, source_version=source.version,
                        active_profile=profile)


def _commit_state(project: Path, state: InstallState, plan: Plan,
                  distribution: Distribution, source: DistributionSource,
                  journal_id: str) -> None:
    """Fold a successfully applied plan into the install state."""

    for identifier in plan.components_removed:
        state.drop_component(identifier)
    for identifier in distribution.effective_component_ids(plan.to_profile or state.active_profile):
        component = distribution.component(identifier)
        entries = plannerlib.managed_entries(component, plan.changes)
        # A CONFLICT leaves the file alone; keep whatever we already knew about
        # it rather than dropping the record and losing its install digest.
        # A pruned path is the opposite case: the distribution no longer ships
        # it, so carrying its record forward left `doctor` reporting MISSING
        # for a file nothing would ever restore (EMP-LC-012).
        dropped = plannerlib.pruned_paths(component, plan.changes)
        known = {item.path: item for item in state.files_for_component(identifier)
                 if item.path not in dropped}
        merged = {item.path: item for item in entries}
        for path, item in known.items():
            merged.setdefault(path, item)
        state.replace_component_files(identifier, merged.values())
        if identifier not in state.installed_components:
            state.installed_components.append(identifier)

    if plan.to_profile and plan.to_profile != state.active_profile:
        state.previous_profile = state.active_profile
        state.active_profile = plan.to_profile
    state.stack_version = source.version
    state.source_version = source.version
    state.last_transaction = journal_id
    statelib.save(project, state)


def plan_profile(project: Path, distribution: Distribution, source: DistributionSource,
                 target_profile: str, *, operation: str,
                 state: InstallState | None = None) -> tuple[Plan, InstallState, legacylib.Adoption]:
    """Resolve the current state (adopting a legacy install) and plan the delta."""

    distribution.profile(target_profile)  # refuse an unknown profile up front
    current = state if state is not None else statelib.load(project)
    adoption = legacylib.Adoption(False, (), (), (), ())
    if current is None:
        current = _fresh_state(source, target_profile)
        adoption = legacylib.adopt(project, distribution, source, target_profile)
        current = legacylib.apply_to_state(current, adoption, stack_version=source.version)
    plan = plannerlib.build_install_plan(project, distribution, source, current,
                                         target_profile, operation=operation)
    return plan, current, adoption


def install(project: Path, target_profile: str, *, dry_run: bool = False,
            operation: str = "init", distribution: Distribution | None = None,
            source: DistributionSource | None = None,
            force_unlock: bool = False) -> OperationResult:
    """Bring `project` to `target_profile`. Idempotent; a no-op changes nothing."""

    project = require_project(project)
    distribution = distribution or manifestlib.load()
    source = source or sourcelib.resolve()
    _blocking_transaction(project)

    plan, state, adoption = plan_profile(project, distribution, source, target_profile,
                                         operation=operation)
    notices = _notices(project, distribution, plan, target_profile, adoption)

    from . import lock as locklib

    if dry_run or plan.is_noop:
        if plan.is_noop and not dry_run:
            # Nothing had to change on disk, but the profile may still need
            # recording. That is a write to the install state, so it takes the
            # lock like every other write — an unlocked commit here could
            # interleave with another operation's own commit.
            if statelib.load(project) is None or state.active_profile != target_profile:
                with locklib.acquire(project, operation, force=force_unlock):
                    state.active_profile = target_profile
                    for identifier in distribution.effective_component_ids(target_profile):
                        if identifier not in state.installed_components:
                            state.installed_components.append(identifier)
                    statelib.save(project, state)
        return OperationResult(operation, plan, applied=False, dry_run=dry_run,
                               state=state, notices=notices, legacy=adoption)

    with locklib.acquire(project, operation, force=force_unlock):
        _blocking_transaction(project)
        plan, state, adoption = plan_profile(project, distribution, source, target_profile,
                                             operation=operation)
        applier = txnlib.Applier(project, distribution, source, plan)
        journal = applier.run(lambda: _commit_state(project, state, plan, distribution,
                                                    source, applier.journal.identifier))
    return OperationResult(operation, plan, applied=True, dry_run=False, state=state,
                           transaction=journal.identifier, notices=notices, legacy=adoption)


def _notices(project: Path, distribution: Distribution, plan: Plan, target_profile: str,
             adoption: legacylib.Adoption) -> list[str]:
    notices: list[str] = []
    if adoption.detected:
        notices.append(
            f"Existing AI Native installation detected ({len(adoption.adopted)} files). "
            "Adopting managed components without overwriting user files.")
    conflicts = [change for change in plan.changes if change.action == plannerlib.CONFLICT]
    if conflicts:
        notices.append(
            f"{len(conflicts)} file(s) you modified were left untouched: "
            + ", ".join(sorted(change.path for change in conflicts)[:5])
            + ("..." if len(conflicts) > 5 else ""))
    if "verified" in distribution.inheritance_chain(target_profile) and \
            not trust_anchor_present(project):
        notices.append(VERIFIED_BOOTSTRAP_NOTICE)
    dormant = [change for change in plan.changes
               if change.kind == "data_root" and change.action == plannerlib.PRESERVE]
    if dormant and target_profile == "standard":
        notices.append(
            "Verified governance is now inactive. Its history is preserved as dormant "
            "state (" + ", ".join(sorted(change.path for change in dormant)) +
            "); `ainative profile switch verified` reactivates it.")
    return notices


def switch(project: Path, target_profile: str, **kwargs) -> OperationResult:
    return install(project, target_profile, operation="profile-switch", **kwargs)


__all__ = ["OperationResult", "install", "switch", "plan_profile", "require_project",
           "trust_anchor_present", "TRUST_ANCHOR_RELATIVE", "VERIFIED_BOOTSTRAP_NOTICE"]
