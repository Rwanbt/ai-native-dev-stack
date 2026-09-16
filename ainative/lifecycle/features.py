"""The feature view of a project: one projection, shared by every read path.

ADR-0017 makes profiles and features orthogonal. A profile is a governance
level; a feature is an optional project-scope capability. State V2 records the
active features, older states do not — and "which features does this project
have?" must never have two answers. Every reader therefore goes through
`project_install_state()`, which is also the single place that knows the V1
compatibility default (a legacy project is a GitHub project until it
explicitly switches).

The projection never writes. `migrate_state()` is its write-side counterpart:
it stamps the current schema and seeds the legacy default exactly once, inside
an existing mutation transaction (state-last, ADR-0009 section 4). It plans no
file changes of its own, so a managed file that is already absent stays
absent through the migration; only an explicit feature transition seeds files.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import manifest as manifestlib
from . import state as statelib
from .errors import LifecycleError


@dataclass(frozen=True)
class EffectiveState:
    """The feature view of one project, projected from whatever is stored."""

    schema_version: int
    active_profile: str
    active_features: tuple[str, ...]
    projected_from_legacy: bool

    def has_feature(self, name: str) -> bool:
        return name in self.active_features

    def feature_objects(self, distribution: manifestlib.Distribution) -> tuple:
        return tuple(distribution.feature(name) for name in self.active_features)


def project_install_state(state: statelib.InstallState | None,
                          distribution: manifestlib.Distribution) -> EffectiveState | None:
    """The features a project effectively has; None when it has no state.

    A V1 state has no `active_features` and projects to the declared legacy
    default (ADR-0017 section 4). A V2 state is validated: an undeclared
    feature refuses as `INSTALL_STATE_CORRUPTED`, two work forges refuse as
    `STATE_CONFLICTING_WORK_FORGE_FEATURES` — fail-closed, never a silent pick.
    """

    if state is None:
        return None
    if state.schema_version < statelib.SCHEMA_VERSION:
        return EffectiveState(schema_version=state.schema_version,
                              active_profile=state.active_profile,
                              active_features=(legacy_default(distribution),),
                              projected_from_legacy=True)
    return EffectiveState(schema_version=state.schema_version,
                          active_profile=state.active_profile,
                          active_features=_validated(state.active_features, distribution),
                          projected_from_legacy=False)


def legacy_default(distribution: manifestlib.Distribution) -> str:
    """The feature a V1 project projects to; declared, never hard-coded."""

    default = distribution.legacy_default_feature
    if not default:
        raise LifecycleError("MANIFEST_INVALID",
                             "the catalogue declares no legacy default feature")
    return default


def _validated(names: list[str], distribution: manifestlib.Distribution) -> tuple[str, ...]:
    ordered = tuple(dict.fromkeys(names))
    for name in ordered:
        try:
            distribution.feature(name)
        except LifecycleError as error:
            if error.code != "FEATURE_UNKNOWN":
                raise
            # A state naming a feature this release does not know is a state
            # problem, not a request problem: the same stance as a newer schema
            # — upgrade the CLI rather than downgrading state.
            raise LifecycleError(
                "INSTALL_STATE_CORRUPTED",
                f"the saved state activates feature {name!r}, which this release "
                "does not know; upgrade the CLI rather than downgrading state") from error
    work_forges = [name for name in ordered if distribution.feature(name).work_forge]
    if len(work_forges) > 1:
        raise LifecycleError(
            "STATE_CONFLICTING_WORK_FORGE_FEATURES",
            "the saved state activates two work forges ("
            + ", ".join(sorted(work_forges))
            + "); a project has at most one — use `ainative feature switch <name>`",
            features=sorted(work_forges))
    for name in ordered:
        for other in distribution.feature(name).conflicts:
            if other in ordered:
                raise LifecycleError(
                    "INSTALL_STATE_CORRUPTED",
                    f"the saved state activates conflicting features "
                    f"{name!r} and {other!r}")
    return ordered


def migrate_state(state: statelib.InstallState,
                  distribution: manifestlib.Distribution) -> statelib.InstallState:
    """Stamp the current schema, seeding the legacy default exactly once.

    Returns the state object it was given (every caller works on the loaded
    object); a state already at the current schema is returned unchanged, so
    running this twice writes the same bytes.
    """

    if state.schema_version >= statelib.SCHEMA_VERSION:
        return state
    if not state.active_features:
        state.active_features = [legacy_default(distribution)]
    state.schema_version = statelib.SCHEMA_VERSION
    return state


def transition(distribution: manifestlib.Distribution, current: tuple[str, ...], *,
               enable: str | None = None, disable: str | None = None,
               switch_to: str | None = None) -> tuple[str, ...]:
    """The feature set a requested transition produces, or a refusal.

    Exactly one of `enable` / `disable` / `switch_to` is given. A transition is
    idempotent: asking for the set the project already has returns it
    unchanged. Enabling a feature that conflicts with an active one refuses
    with the remedy stated — the conflict is never resolved by an implicit
    disable. `switch_to="none"` is the Generic Git shape: it removes every
    work forge and nothing else.
    """

    requested = [value for value in (enable, disable) if value is not None]
    if len(requested) + (1 if switch_to is not None else 0) != 1:
        raise ValueError(
            "a feature transition takes exactly one of enable/disable/switch_to")

    if enable is not None:
        candidate = distribution.feature(enable)
        for name in current:
            if name in candidate.conflicts:
                raise LifecycleError(
                    "FEATURE_CONFLICT",
                    f"feature {enable!r} conflicts with the active feature {name!r}; "
                    f"use `ainative feature switch {enable}`",
                    requested=enable, active=name)
        return current if enable in current else current + (enable,)

    if disable is not None:
        distribution.feature(disable)
        return tuple(name for name in current if name != disable)

    if switch_to == "none":
        return tuple(name for name in current if not distribution.feature(name).work_forge)

    distribution.feature(switch_to)
    conflicts = set(distribution.feature(switch_to).conflicts)
    kept = tuple(name for name in current if name not in conflicts and name != switch_to)
    return kept + (switch_to,)


__all__ = ["EffectiveState", "project_install_state", "legacy_default",
           "migrate_state", "transition"]
