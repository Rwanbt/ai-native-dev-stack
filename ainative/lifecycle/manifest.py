"""Load and validate the component and profile manifests.

The manifests are data, and data reaches `unlink()`. Everything here therefore
validates before it returns: an unknown kind, an unknown ownership class, a
missing parent, an inheritance cycle or a path that leaves the project root is
a refusal, not a value a later stage has to re-check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import LifecycleError
from .paths import collision_key, validate_relative

DATA_DIR = Path(__file__).resolve().parent / "data"

KIND_TREE = "tree"
KIND_FILE = "file"
KIND_TEMPLATE = "template"
KIND_EXTERNAL_BLOCK = "external_block"
KIND_MARKER = "marker"
KIND_DATA_ROOT = "data_root"
KINDS = (KIND_TREE, KIND_FILE, KIND_TEMPLATE, KIND_EXTERNAL_BLOCK, KIND_MARKER, KIND_DATA_ROOT)

MANAGED_IMMUTABLE = "MANAGED_IMMUTABLE"
MANAGED_MUTABLE = "MANAGED_MUTABLE"
USER_DATA = "USER_DATA"
EXTERNAL_CONFIG = "EXTERNAL_CONFIG"
OWNERSHIPS = (MANAGED_IMMUTABLE, MANAGED_MUTABLE, USER_DATA, EXTERNAL_CONFIG)

# Which kinds need which fields. Stated once so a malformed manifest is caught
# by the same rule the documentation describes.
_REQUIRED_FIELDS = {
    KIND_TREE: ("source", "destination"),
    KIND_FILE: ("source", "destination"),
    KIND_TEMPLATE: ("source", "destination"),
    KIND_EXTERNAL_BLOCK: ("destination", "marker", "lines"),
    KIND_MARKER: ("destination",),
    KIND_DATA_ROOT: ("paths",),
}


@dataclass(frozen=True)
class Component:
    identifier: str
    version: int
    kind: str
    ownership: str
    required: bool
    title: str
    description: str
    source: str | None = None
    destination: str | None = None
    include: tuple[str, ...] = ()
    executable: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    marker: str | None = None
    comment_prefix: str = "#"
    lines: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()

    def applies_to(self, platform: str) -> bool:
        return not self.platforms or platform in self.platforms


@dataclass(frozen=True)
class Profile:
    name: str
    extends: str | None
    title: str
    summary: str
    recommended_for: str
    components: tuple[str, ...]


@dataclass(frozen=True)
class Distribution:
    """The component and profile catalogue, already validated."""

    components: Mapping[str, Component]
    profiles: Mapping[str, Profile]
    default_profile: str
    schema_version: int = 1
    _cache: dict = field(default_factory=dict, compare=False, repr=False)

    def profile(self, name: str) -> Profile:
        try:
            return self.profiles[name]
        except KeyError:
            known = ", ".join(sorted(self.profiles))
            raise LifecycleError("PROFILE_INVALID",
                                 f"unknown profile {name!r} (known: {known})") from None

    def component(self, identifier: str) -> Component:
        try:
            return self.components[identifier]
        except KeyError:
            raise LifecycleError("COMPONENT_UNKNOWN",
                                 f"profile references unknown component {identifier!r}") from None

    def effective_components(self, name: str) -> tuple[Component, ...]:
        """Parent components first, then the profile's own, deduplicated."""

        return tuple(self.component(identifier)
                     for identifier in self.effective_component_ids(name))

    def effective_component_ids(self, name: str) -> tuple[str, ...]:
        ordered: list[str] = []
        for profile_name in self.inheritance_chain(name):
            for identifier in self.profiles[profile_name].components:
                self.component(identifier)  # refuse an unknown id at resolve time
                if identifier not in ordered:
                    ordered.append(identifier)
        return tuple(ordered)

    def inheritance_chain(self, name: str) -> tuple[str, ...]:
        """From the root ancestor down to `name`. Refuses cycles."""

        chain: list[str] = []
        seen: set[str] = set()
        current: str | None = name
        while current is not None:
            if current in seen:
                raise LifecycleError("PROFILE_INVALID",
                                     f"inheritance cycle at profile {current!r}")
            seen.add(current)
            profile = self.profile(current)
            chain.append(current)
            current = profile.extends
        return tuple(reversed(chain))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LifecycleError("MANIFEST_INVALID", f"cannot read {path.name}: {error}") from error
    if not isinstance(payload, dict):
        raise LifecycleError("MANIFEST_INVALID", f"{path.name} is not a JSON object")
    return payload


def _strings(raw: Any, field_name: str, identifier: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise LifecycleError("MANIFEST_INVALID",
                             f"component {identifier!r}: {field_name} must be a list of strings")
    return tuple(raw)


def _build_component(identifier: str, raw: Any) -> Component:
    if not isinstance(raw, dict):
        raise LifecycleError("MANIFEST_INVALID", f"component {identifier!r} is not an object")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise LifecycleError("MANIFEST_INVALID",
                             f"component {identifier!r}: unknown kind {kind!r}")
    ownership = raw.get("ownership")
    if ownership not in OWNERSHIPS:
        raise LifecycleError("MANIFEST_INVALID",
                             f"component {identifier!r}: unknown ownership {ownership!r}")
    for name in _REQUIRED_FIELDS[kind]:
        if not raw.get(name):
            raise LifecycleError("MANIFEST_INVALID",
                                 f"component {identifier!r}: {kind} requires {name!r}")

    destination = raw.get("destination")
    if destination is not None:
        validate_relative(destination)
    paths = _strings(raw.get("paths"), "paths", identifier)
    for path in paths:
        validate_relative(path)
    include = _strings(raw.get("include"), "include", identifier)
    for entry in include:
        validate_relative(entry)

    return Component(
        identifier=identifier,
        version=int(raw.get("version", 1)),
        kind=kind,
        ownership=ownership,
        required=bool(raw.get("required", False)),
        title=str(raw.get("title", identifier)),
        description=str(raw.get("description", "")),
        source=raw.get("source"),
        destination=destination,
        include=include,
        executable=_strings(raw.get("executable"), "executable", identifier),
        paths=paths,
        marker=raw.get("marker"),
        comment_prefix=str(raw.get("comment_prefix", "#")),
        lines=_strings(raw.get("lines"), "lines", identifier),
        platforms=_strings(raw.get("platforms"), "platforms", identifier),
    )


def _build_profile(name: str, raw: Any) -> Profile:
    if not isinstance(raw, dict):
        raise LifecycleError("MANIFEST_INVALID", f"profile {name!r} is not an object")
    extends = raw.get("extends")
    if extends is not None and not isinstance(extends, str):
        raise LifecycleError("MANIFEST_INVALID", f"profile {name!r}: extends must be a string")
    return Profile(
        name=name,
        extends=extends,
        title=str(raw.get("title", name.title())),
        summary=str(raw.get("summary", "")),
        recommended_for=str(raw.get("recommended_for", "")),
        components=_strings(raw.get("components"), "components", name),
    )


def _reject_collisions(components: Mapping[str, Component]) -> None:
    """Two destinations that differ only in case are one path on Windows.

    Trees are checked too. Excluding them left the guard blind to exactly the
    case it exists for — two directory components landing on the same path
    would have interleaved, each pruning the other's files (EMP-LC-015).
    """

    seen: dict[str, str] = {}
    for identifier, component in components.items():
        if component.kind == KIND_DATA_ROOT or not component.destination:
            continue
        key = collision_key(component.destination)
        if key in seen and seen[key] != identifier:
            raise LifecycleError(
                "MANIFEST_INVALID",
                f"components {seen[key]!r} and {identifier!r} claim the same destination "
                f"on a case-insensitive filesystem: {component.destination}")
        seen[key] = identifier


def load(data_dir: Path | None = None) -> Distribution:
    """Read, validate and link the two manifests."""

    directory = Path(data_dir) if data_dir else DATA_DIR
    component_payload = _read_json(directory / "components.json")
    profile_payload = _read_json(directory / "profiles.json")

    raw_components = component_payload.get("components")
    if not isinstance(raw_components, dict) or not raw_components:
        raise LifecycleError("MANIFEST_INVALID", "components.json declares no components")
    components = {identifier: _build_component(identifier, raw)
                  for identifier, raw in sorted(raw_components.items())}
    _reject_collisions(components)

    raw_profiles = profile_payload.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise LifecycleError("MANIFEST_INVALID", "profiles.json declares no profiles")
    profiles = {name: _build_profile(name, raw) for name, raw in sorted(raw_profiles.items())}

    default = profile_payload.get("default", "standard")
    if default not in profiles:
        raise LifecycleError("MANIFEST_INVALID", f"default profile {default!r} is not declared")

    distribution = Distribution(components=components, profiles=profiles, default_profile=default,
                                schema_version=int(profile_payload.get("schema_version", 1)))
    for name in profiles:
        distribution.effective_component_ids(name)  # proves the graph resolves
    return distribution


__all__ = [
    "Component", "Profile", "Distribution", "load", "DATA_DIR",
    "KIND_TREE", "KIND_FILE", "KIND_TEMPLATE", "KIND_EXTERNAL_BLOCK",
    "KIND_MARKER", "KIND_DATA_ROOT", "KINDS",
    "MANAGED_IMMUTABLE", "MANAGED_MUTABLE", "USER_DATA", "EXTERNAL_CONFIG", "OWNERSHIPS",
]
