"""Turn a desired profile into an explicit, reviewable list of changes.

Nothing here touches the filesystem beyond reading it. That is the whole point:
`--dry-run` is the planner with the applier not called, so the plan a user
inspects is byte-for-byte the plan that would have run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from . import digest as digestlib
from . import manifest as manifestlib
from .errors import LifecycleError
from .external import BlockSpec
from .manifest import Component, Distribution
from .paths import resolve_within
from .source import DistributionSource
from .state import InstallState, ManagedFile

# Change actions. `SKIP` and `PRESERVE` are recorded, not silent: a user who
# edited a file must see that the operation noticed and stepped around it.
CREATE = "CREATE"
REPLACE = "REPLACE"
REMOVE = "REMOVE"
SKIP = "SKIP"
PRESERVE = "PRESERVE"
CONFLICT = "CONFLICT"
BLOCK_WRITE = "BLOCK_WRITE"
BLOCK_REMOVE = "BLOCK_REMOVE"

MUTATING_ACTIONS = (CREATE, REPLACE, REMOVE, BLOCK_WRITE, BLOCK_REMOVE)


@dataclass(frozen=True)
class Change:
    action: str
    path: str                    # project-relative POSIX
    component: str
    ownership: str
    reason: str = ""
    source: str | None = None    # distribution-relative source path
    digest: str | None = None    # digest the file will hold after the change
    kind: str = "file"
    # True when the distribution no longer ships this path. The state must then
    # stop recording it whatever happened to the file, or `doctor` reports it
    # MISSING forever and `repair` cannot clear it (EMP-LC-012).
    pruned: bool = False

    def mutates(self) -> bool:
        return self.action in MUTATING_ACTIONS

    def to_record(self) -> dict:
        return {"action": self.action, "path": self.path, "component": self.component,
                "ownership": self.ownership, "reason": self.reason, "kind": self.kind,
                "pruned": self.pruned}


@dataclass
class Plan:
    operation: str
    project: Path
    from_profile: str | None
    to_profile: str | None
    changes: list[Change] = field(default_factory=list)
    components_added: list[str] = field(default_factory=list)
    components_removed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def mutating(self) -> list[Change]:
        return [change for change in self.changes if change.mutates()]

    @property
    def is_noop(self) -> bool:
        return not self.mutating

    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for change in self.changes:
            tally[change.action] = tally.get(change.action, 0) + 1
        return tally

    def to_record(self) -> dict:
        return {
            "operation": self.operation,
            "project": str(self.project),
            "from_profile": self.from_profile,
            "to_profile": self.to_profile,
            "components_added": sorted(self.components_added),
            "components_removed": sorted(self.components_removed),
            "counts": self.counts(),
            "changes": [change.to_record() for change in self.changes],
            "notes": list(self.notes),
            "no_op": self.is_noop,
        }


def block_spec(component: Component) -> BlockSpec:
    return BlockSpec(marker=component.marker or component.identifier,
                     comment_prefix=component.comment_prefix, lines=component.lines)


def marker_payload(component: Component, source: DistributionSource, profile: str) -> str:
    """The body of a `marker` component — a fact about activation, not authority.

    It deliberately records no trust, approval or verdict: ADR-0009 §2 forbids
    the lifecycle layer from writing anything an authority evaluation reads.
    """

    return json.dumps({
        "schema_version": 1,
        "component": component.identifier,
        "profile": profile,
        "stack_version": source.version,
        "authority": "none — activation record only, never a trust or convergence fact",
    }, indent=2, sort_keys=True) + "\n"


def _tree_entries(component: Component, source: DistributionSource) -> list[tuple[str, str]]:
    """(project-relative destination, distribution-relative source) for a tree."""

    root = source.path(component.source or "")
    if not root.is_dir():
        return []
    entries: list[tuple[str, str]] = []
    if component.include:
        for name in component.include:
            if (root / name).is_file():
                entries.append((f"{component.destination}/{name}",
                                f"{component.source}/{name}"))
        return sorted(entries)
    for item in sorted(root.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        if "__pycache__" in item.parts or item.name.endswith(".pyc"):
            continue
        relative = item.relative_to(root).as_posix()
        entries.append((f"{component.destination}/{relative}",
                        f"{component.source}/{relative}"))
    return sorted(entries)


def component_files(component: Component,
                    source: DistributionSource) -> list[tuple[str, str | None]]:
    """Every destination a component owns, with its distribution-relative source.

    The source is recorded per file rather than per component, so the applier
    never has to reconstruct a path by string-slicing a destination prefix.
    """

    if component.kind == manifestlib.KIND_TREE:
        return list(_tree_entries(component, source))
    if component.kind in (manifestlib.KIND_FILE, manifestlib.KIND_TEMPLATE):
        return [(component.destination or "", component.source)]
    if component.kind == manifestlib.KIND_MARKER:
        return [(component.destination or "", None)]
    return []


def _install_change(project: Path, destination: str, source_relative: str | None,
                    component: Component, source: DistributionSource,
                    state: InstallState, payload: bytes | None) -> Change:
    """One file's decision, taken from ownership and the recorded digest."""

    target = resolve_within(project, destination)
    known = state.file_for(destination)
    if payload is None and source_relative is not None:
        try:
            payload = source.path(source_relative).read_bytes()
        except OSError as error:
            raise LifecycleError(
                "APPLY_FAILED",
                f"cannot read distribution file {source_relative}: {error}") from error
    new_digest = digestlib.digest_bytes(payload) if payload is not None else None

    if component.kind == manifestlib.KIND_TEMPLATE:
        # The copy belongs to the user from the moment it exists.
        if target.exists():
            return Change(SKIP, destination, component.identifier, component.ownership,
                          "user-owned copy already present", source_relative, None)
        return Change(CREATE, destination, component.identifier, component.ownership,
                      "seeded from the shipped template", source_relative, new_digest)

    if not target.exists():
        return Change(CREATE, destination, component.identifier, component.ownership,
                      "absent", source_relative, new_digest)

    current = digestlib.digest_file(target)
    if current is not None and current == new_digest:
        return Change(SKIP, destination, component.identifier, component.ownership,
                      "already current", source_relative, new_digest)

    status = digestlib.classify(target, known.digest_at_install if known else None)
    if known is None:
        # Present, differing, and never recorded: it is not ours to replace.
        return Change(CONFLICT, destination, component.identifier, component.ownership,
                      "exists but was not installed by ainative", source_relative, None)
    if not known.created_by_ainative:
        # Adopted from a legacy install because it sat where a managed file
        # goes, but its bytes were never ours. Recording it made it trackable;
        # it did not make it ours to overwrite.
        return Change(CONFLICT, destination, component.identifier, component.ownership,
                      "adopted but not written by ainative - left in place",
                      source_relative, None)
    if digestlib.is_safe_to_replace(status):
        return Change(REPLACE, destination, component.identifier, component.ownership,
                      "managed file is unchanged since install", source_relative, new_digest)
    return Change(CONFLICT, destination, component.identifier, component.ownership,
                  f"user-modified ({status}) - left in place", source_relative, None)


def _prune_changes(project: Path, component: Component, wanted: Iterable[str],
                   state: InstallState) -> list[Change]:
    """Remove files this component installed that the distribution dropped.

    Only unchanged files are pruned. The old installer removed everything the
    source no longer had, which deleted a user's edit to a shipped skill.
    """

    keep = set(wanted)
    changes: list[Change] = []
    for entry in state.files_for_component(component.identifier):
        if entry.path in keep or entry.kind != "file":
            continue
        target = resolve_within(project, entry.path)
        status = digestlib.classify(target, entry.digest_at_install)
        if status == digestlib.MISSING:
            changes.append(Change(SKIP, entry.path, component.identifier, entry.ownership,
                                  "removed upstream and already absent", pruned=True))
        elif digestlib.is_safe_to_remove(status):
            changes.append(Change(REMOVE, entry.path, component.identifier, entry.ownership,
                                  "removed upstream", pruned=True))
        else:
            changes.append(Change(PRESERVE, entry.path, component.identifier, entry.ownership,
                                  f"removed upstream but {status} - kept on disk, "
                                  "no longer tracked", pruned=True))
    return changes


def plan_component_install(project: Path, component: Component, source: DistributionSource,
                           state: InstallState, profile: str) -> list[Change]:
    if component.kind == manifestlib.KIND_DATA_ROOT:
        return [Change(SKIP, path, component.identifier, component.ownership,
                       "user data root — declared, never written", kind="data_root")
                for path in component.paths]

    if component.kind == manifestlib.KIND_EXTERNAL_BLOCK:
        destination = component.destination or ""
        target = resolve_within(project, destination)
        _, changed = _external_preview(target, component)
        action = BLOCK_WRITE if changed else SKIP
        return [Change(action, destination, component.identifier, component.ownership,
                       "managed region in a file the stack does not own",
                       kind="external_block")]

    changes: list[Change] = []
    wanted: list[str] = []
    for destination, source_relative in component_files(component, source):
        if not destination:
            continue
        payload = None
        if component.kind == manifestlib.KIND_MARKER:
            payload = marker_payload(component, source, profile).encode("utf-8")
        changes.append(_install_change(project, destination, source_relative, component,
                                       source, state, payload))
        wanted.append(destination)
    changes.extend(_prune_changes(project, component, wanted, state))
    return changes


def _external_preview(target: Path, component: Component) -> tuple[str, bool]:
    from . import external
    return external.apply(target, block_spec(component))


def plan_component_removal(project: Path, component: Component, state: InstallState, *,
                           purge: bool) -> list[Change]:
    """What removing a component would do. `purge` also takes user data."""

    changes: list[Change] = []
    for entry in state.files_for_component(component.identifier):
        target = resolve_within(project, entry.path)
        if entry.kind == "external_block":
            changes.append(Change(BLOCK_REMOVE, entry.path, component.identifier,
                                  entry.ownership, "remove only the managed region",
                                  kind="external_block"))
            continue
        if entry.kind == "data_root":
            action = REMOVE if purge else PRESERVE
            reason = "purge requested" if purge else "user data — preserved"
            changes.append(Change(action, entry.path, component.identifier, entry.ownership,
                                  reason, kind="data_root"))
            continue
        if entry.ownership == manifestlib.USER_DATA:
            # `--purge` deletes declared *data roots* (handled above), not every
            # file that happens to be user-owned. `tools/ai_docs/config.sh` is
            # the user's machine config, seeded from a template; the retention
            # table keeps it under purge and the code now agrees.
            changes.append(Change(PRESERVE, entry.path, component.identifier, entry.ownership,
                                  "user data - preserved"))
            continue
        if not entry.created_by_ainative:
            # Adoption may never make the uninstaller delete a file the stack
            # did not write (ADR-0009, consequences). `--purge` does not lift
            # this: purge removes AI Native's own data roots, not a file whose
            # bytes were always the user's.
            changes.append(Change(PRESERVE, entry.path, component.identifier, entry.ownership,
                                  "adopted but not written by ainative - preserved"))
            continue
        # The digest decides, and `--purge` does not override it. It used to:
        # a managed file the user had edited was deleted under purge, silently,
        # while the retention table promised it was kept (EMP-LC-018). Purge's
        # extra reach is over declared data roots, nothing else.
        status = digestlib.classify(target, entry.digest_at_install)
        if status == digestlib.MISSING:
            changes.append(Change(SKIP, entry.path, component.identifier, entry.ownership,
                                  "already absent"))
        elif digestlib.is_safe_to_remove(status):
            changes.append(Change(REMOVE, entry.path, component.identifier, entry.ownership,
                                  "unchanged since install"))
        else:
            changes.append(Change(PRESERVE, entry.path, component.identifier, entry.ownership,
                                  f"{status} - preserved"))
    return changes


def build_install_plan(project: Path, distribution: Distribution, source: DistributionSource,
                       state: InstallState, target_profile: str, *,
                       operation: str) -> Plan:
    """Install or switch to `target_profile`, changing only what differs."""

    wanted = distribution.effective_component_ids(target_profile)
    present = list(state.installed_components)
    plan = Plan(operation=operation, project=project,
                from_profile=state.active_profile if present else None,
                to_profile=target_profile)

    for identifier in wanted:
        component = distribution.component(identifier)
        plan.changes.extend(plan_component_install(project, component, source, state,
                                                   target_profile))
        if identifier not in present:
            plan.components_added.append(identifier)

    for identifier in present:
        if identifier in wanted:
            continue
        component = distribution.components.get(identifier)
        if component is None:
            plan.notes.append(f"component {identifier} is installed but no longer declared")
            continue
        if component.ownership == manifestlib.USER_DATA:
            # Leaving a profile never deletes its history (ADR-0009 §5).
            plan.changes.extend(
                Change(PRESERVE, path, identifier, component.ownership,
                       "dormant verified state — preserved across the downgrade",
                       kind="data_root")
                for path in component.paths)
            plan.components_removed.append(identifier)
            continue
        plan.changes.extend(plan_component_removal(project, component, state, purge=False))
        plan.components_removed.append(identifier)

    return plan


def build_uninstall_plan(project: Path, distribution: Distribution, state: InstallState, *,
                         purge: bool) -> Plan:
    plan = Plan(operation="uninstall" + ("-purge" if purge else ""), project=project,
                from_profile=state.active_profile, to_profile=None)
    for identifier in state.installed_components:
        component = distribution.components.get(identifier)
        if component is None:
            plan.notes.append(f"component {identifier} is installed but no longer declared")
            continue
        plan.changes.extend(plan_component_removal(project, component, state, purge=purge))
        plan.components_removed.append(identifier)
    # Orphans: recorded files whose component vanished from the manifests.
    known = set(state.installed_components)
    orphans = [entry for entry in state.managed_files if entry.component not in known]
    for entry in orphans:
        status = digestlib.classify(resolve_within(project, entry.path), entry.digest_at_install)
        action = REMOVE if (purge or digestlib.is_safe_to_remove(status)) else PRESERVE
        plan.changes.append(Change(action, entry.path, entry.component, entry.ownership,
                                   "orphaned managed file", kind=entry.kind))
    return plan


def pruned_paths(component: Component, changes: Sequence[Change]) -> set[str]:
    """Paths the distribution no longer ships, whatever became of the file."""

    return {change.path for change in changes
            if change.component == component.identifier and change.pruned}


def managed_entries(component: Component, changes: Sequence[Change]) -> list[ManagedFile]:
    """The state records a successful component install should produce."""

    entries: list[ManagedFile] = []
    for change in changes:
        if change.component != component.identifier:
            continue
        if change.action in (REMOVE,) or change.pruned:
            continue
        if change.kind == "data_root":
            entries.append(ManagedFile(change.path, component.identifier, component.ownership,
                                       None, created_by_ainative=False, kind="data_root"))
            continue
        if change.kind == "external_block":
            entries.append(ManagedFile(change.path, component.identifier, component.ownership,
                                       None, created_by_ainative=False, kind="external_block"))
            continue
        if change.action == CONFLICT:
            continue
        entries.append(ManagedFile(change.path, component.identifier, component.ownership,
                                   change.digest, created_by_ainative=True, kind="file"))
    return entries


__all__ = [
    "CREATE", "REPLACE", "REMOVE", "SKIP", "PRESERVE", "CONFLICT",
    "BLOCK_WRITE", "BLOCK_REMOVE", "MUTATING_ACTIONS",
    "Change", "Plan", "block_spec", "marker_payload", "component_files",
    "plan_component_install", "plan_component_removal",
    "build_install_plan", "build_uninstall_plan", "managed_entries",
]
