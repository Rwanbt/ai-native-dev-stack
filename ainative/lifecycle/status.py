"""What is installed, in one screen or one JSON document.

`status` is the command a user runs when something is confusing, so it must be
fast and it must be truthful about what it does not know. It reads the install
state and the filesystem; it consults the update cache but never the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import manifest as manifestlib
from . import recovery as recoverylib
from . import state as statelib
from . import updater as updaterlib
from .manifest import Distribution

CHECK = "OK"
CROSS = "--"


@dataclass
class Status:
    project: Path
    installed: bool
    stack_version: str | None
    active_profile: str | None
    previous_profile: str | None
    components: list[dict] = field(default_factory=list)
    healthy: bool = True
    lifecycle_notes: list[str] = field(default_factory=list)
    verified: dict = field(default_factory=dict)
    update: dict | None = None
    counts: dict = field(default_factory=dict)

    def to_record(self) -> dict:
        return {
            "project": str(self.project),
            "installed": self.installed,
            "stack_version": self.stack_version,
            "profile": self.active_profile,
            "previous_profile": self.previous_profile,
            "components": self.components,
            "lifecycle": {"healthy": self.healthy, "notes": list(self.lifecycle_notes),
                          "findings": self.counts},
            "verified": self.verified,
            "updates": self.update,
        }

    def render(self) -> str:
        lines = [f"AI Native Dev Stack {self.stack_version or '(not installed)'}", ""]
        if not self.installed:
            lines.append("Profile\n  none — run `ainative init` to install")
            return "\n".join(lines)
        lines.append("Profile")
        lines.append(f"  {self.active_profile}")
        lines.append("")
        lines.append("Components")
        for item in self.components:
            mark = CHECK if item["status"] == recoverylib.OK else CROSS
            suffix = "" if item["status"] == recoverylib.OK else f"  ({item['status']})"
            lines.append(f"  {mark} {item['title']}{suffix}")
        lines.append("")
        lines.append("Lifecycle")
        lines.append(f"  {'healthy' if self.healthy else 'needs attention'}")
        for note in self.lifecycle_notes:
            lines.append(f"  - {note}")
        if self.verified:
            lines.append("")
            lines.append("Verified")
            lines.append(f"  trust state: {self.verified.get('trust_state')}")
            lines.append(f"  historical data: {self.verified.get('historical_data')}")
        if self.update:
            lines.append("")
            lines.append("Updates")
            latest = self.update.get("latest")
            if self.update.get("status") == updaterlib.UPDATE_AVAILABLE and latest:
                lines.append(f"  {latest} available")
            else:
                lines.append(f"  {self.update.get('status', 'unknown').lower()}")
        return "\n".join(lines)


def _component_rows(distribution: Distribution, state: statelib.InstallState,
                    diagnosis: recoverylib.Diagnosis) -> list[dict]:
    by_component: dict[str, list[str]] = {}
    for finding in diagnosis.findings:
        by_component.setdefault(finding["component"], []).append(finding["status"])

    rows: list[dict] = []
    for identifier in state.installed_components:
        component = distribution.components.get(identifier)
        statuses = by_component.get(identifier, [])
        worst = recoverylib.OK
        for candidate in (recoverylib.CORRUPTED, recoverylib.MISSING, recoverylib.DUPLICATE,
                          recoverylib.ORPHANED, recoverylib.USER_MODIFIED):
            if candidate in statuses:
                worst = candidate
                break
        rows.append({"id": identifier,
                     "title": component.title if component else identifier,
                     "status": worst, "files": len(statuses)})
    return sorted(rows, key=lambda item: item["id"])


def _verified_section(project: Path, distribution: Distribution,
                      state: statelib.InstallState) -> dict:
    from . import installer as installerlib

    chain = distribution.inheritance_chain(state.active_profile) \
        if state.active_profile in distribution.profiles else ()
    if "verified" not in chain and "verified" not in state.installed_components:
        # Report dormant history even when the active profile is Standard: it is
        # the fact a user needs to know before they purge anything.
        dormant = _verified_data_present(project, distribution)
        if not dormant:
            return {}
        return {"active": False, "trust_state": "not applicable (Standard profile)",
                "historical_data": "present (dormant)",
                "note": "`ainative profile switch verified` reactivates governance."}
    return {
        "active": True,
        "trust_state": "configured" if installerlib.trust_anchor_present(project)
        else "not bootstrapped — run `ainative trust bootstrap`",
        "historical_data": "present" if _verified_data_present(project, distribution)
        else "none yet",
    }


def _verified_data_present(project: Path, distribution: Distribution) -> bool:
    for component in distribution.components.values():
        if component.kind != manifestlib.KIND_DATA_ROOT:
            continue
        for relative in component.paths:
            candidate = project / relative
            if candidate.is_dir() and any(candidate.iterdir()):
                return True
    return False


def build(project: Path, *, distribution: Distribution | None = None,
          check_updates: bool = False) -> Status:
    from . import installer as installerlib

    project = installerlib.require_project(project)
    distribution = distribution or manifestlib.load()
    diagnosis = recoverylib.diagnose(project, distribution=distribution)
    state = statelib.load(project) if diagnosis.installed else None

    if state is None:
        return Status(project=project, installed=False, stack_version=None,
                      active_profile=None, previous_profile=None,
                      healthy=diagnosis.healthy,
                      lifecycle_notes=list(diagnosis.notes),
                      update=updaterlib.cached_notice(project, allow_network=check_updates))

    notes = list(diagnosis.notes)
    if diagnosis.transactions:
        notes.append(f"{len(diagnosis.transactions)} interrupted transaction(s) — "
                     "run `ainative repair`")
    if diagnosis.lock and diagnosis.lock.get("stale_suspect"):
        notes.append("a lifecycle lock is present and may be stale")

    return Status(
        project=project, installed=True, stack_version=state.stack_version,
        active_profile=state.active_profile, previous_profile=state.previous_profile,
        components=_component_rows(distribution, state, diagnosis),
        healthy=diagnosis.healthy, lifecycle_notes=notes,
        verified=_verified_section(project, distribution, state),
        update=updaterlib.cached_notice(project, allow_network=check_updates),
        counts=diagnosis.counts())


__all__ = ["Status", "build"]
