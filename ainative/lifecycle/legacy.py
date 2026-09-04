"""Adopt an installation that predates the lifecycle state.

Users installed this stack with `install.py` long before anything recorded what
it wrote. Those projects hold real managed files and no manifest. Adoption turns
them into a lifecycle-managed install without ever claiming ownership it cannot
prove.

The rule (ADR-0009, consequences) is one-way: a file may be adopted as
`MANAGED_IMMUTABLE` only when its bytes are exactly the bytes the distribution
currently ships. Anything else is adopted as `MANAGED_MUTABLE` — recorded, so a
later update can reason about it, but with `digest_at_install` set to what is on
disk, which makes it `UNCHANGED` now and protects it the moment the user edits
it. A file the distribution does not ship at all is not adopted; it stays the
user's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import digest as digestlib
from . import manifest as manifestlib
from . import planner as plannerlib
from .external import BlockSpec, count as block_count
from .manifest import Distribution
from .paths import resolve_within
from .source import DistributionSource
from .state import InstallState, ManagedFile

# Evidence that some version of the stack was installed here without a state
# file. Any one of these is enough to ask the adoption question.
LEGACY_MARKERS = (
    "tools/ai_docs/generate_all.py",
    ".claude/skills",
    ".agents/skills",
    ".stack-lock.json",
)


@dataclass(frozen=True)
class Adoption:
    detected: bool
    markers: tuple[str, ...]
    adopted: tuple[ManagedFile, ...]
    components: tuple[str, ...]
    unmanaged: tuple[str, ...]

    def to_record(self) -> dict:
        return {
            "legacy_install": self.detected,
            "markers": list(self.markers),
            "adopted_files": len(self.adopted),
            "adopted_components": list(self.components),
            "left_unmanaged": list(self.unmanaged),
        }


def detect(project: Path) -> tuple[str, ...]:
    """Markers of a pre-lifecycle install. Empty when the project is clean."""

    return tuple(marker for marker in LEGACY_MARKERS if (project / marker).exists())


def _adopt_component(project: Path, component, source: DistributionSource,
                     ) -> tuple[list[ManagedFile], list[str]]:
    adopted: list[ManagedFile] = []
    unmanaged: list[str] = []

    if component.kind == manifestlib.KIND_DATA_ROOT:
        for path in component.paths:
            if (project / path).exists():
                adopted.append(ManagedFile(path, component.identifier, component.ownership,
                                           None, created_by_ainative=False, kind="data_root"))
        return adopted, unmanaged

    if component.kind == manifestlib.KIND_EXTERNAL_BLOCK:
        destination = component.destination or ""
        spec = BlockSpec(component.marker or component.identifier,
                         component.comment_prefix, component.lines)
        if block_count(resolve_within(project, destination), spec):
            adopted.append(ManagedFile(destination, component.identifier, component.ownership,
                                       None, created_by_ainative=False, kind="external_block"))
        return adopted, unmanaged

    for destination, source_relative in plannerlib.component_files(component, source):
        if not destination:
            continue
        target = resolve_within(project, destination)
        current = digestlib.digest_file(target)
        if current is None:
            continue  # absent: the install plan will create it normally
        if component.ownership == manifestlib.USER_DATA:
            adopted.append(ManagedFile(destination, component.identifier, component.ownership,
                                       current, created_by_ainative=False))
            continue
        shipped = None
        if source_relative is not None:
            try:
                shipped = digestlib.digest_bytes(source.path(source_relative).read_bytes())
            except OSError:
                shipped = None
        if shipped is not None and shipped == current:
            # Byte-identical to what we ship: provably ours to manage.
            adopted.append(ManagedFile(destination, component.identifier, component.ownership,
                                       current, created_by_ainative=False))
        else:
            # Present but different. Record it as mutable at its current digest:
            # it is now UNCHANGED, so nothing will delete it, and the moment the
            # user edits it again it becomes USER_MODIFIED and stays protected.
            adopted.append(ManagedFile(destination, component.identifier,
                                       manifestlib.MANAGED_MUTABLE, current,
                                       created_by_ainative=False))
            unmanaged.append(destination)
    return adopted, unmanaged


def adopt(project: Path, distribution: Distribution, source: DistributionSource,
          profile: str) -> Adoption:
    """Build the state a legacy install should have had, without writing anything."""

    markers = detect(project)
    if not markers:
        return Adoption(False, (), (), (), ())

    adopted: list[ManagedFile] = []
    components: list[str] = []
    unmanaged: list[str] = []
    for identifier in distribution.effective_component_ids(profile):
        component = distribution.component(identifier)
        entries, skipped = _adopt_component(project, component, source)
        if entries:
            components.append(identifier)
            adopted.extend(entries)
        unmanaged.extend(skipped)
    return Adoption(True, markers, tuple(adopted), tuple(components), tuple(unmanaged))


def apply_to_state(state: InstallState, adoption: Adoption, *, stack_version: str) -> InstallState:
    """Fold an adoption into a fresh state, ready for the install plan to build on."""

    if not adoption.detected:
        return state
    state.managed_files = list(adoption.adopted)
    state.installed_components = list(adoption.components)
    state.adopted_from_legacy = True
    state.stack_version = stack_version
    state.source_version = stack_version
    return state


__all__ = ["Adoption", "detect", "adopt", "apply_to_state", "LEGACY_MARKERS"]
