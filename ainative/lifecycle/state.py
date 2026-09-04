"""The install state: what is installed, where it came from, and what it hashed.

This file is the only record that distinguishes a file the stack wrote from a
file the user wrote. It is written last in every transaction (ADR-0009 §4), so
an interrupted run leaves the previous valid state behind rather than a state
describing an install that did not finish.

Three version numbers appear here and they are deliberately separate:
`schema_version` (this file's shape), `stack_version` (the release installed),
and the Work Plane runtime version (the package's own). Conflating them is how
a migration ends up keyed on the wrong number.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .errors import LifecycleError

SCHEMA_VERSION = 1

LIFECYCLE_DIRNAME = Path(".ai-native") / "lifecycle"
STATE_RELATIVE = LIFECYCLE_DIRNAME / "state.json"
TRANSACTIONS_RELATIVE = LIFECYCLE_DIRNAME / "transactions"
BACKUPS_RELATIVE = LIFECYCLE_DIRNAME / "backups"
UPDATE_CACHE_RELATIVE = LIFECYCLE_DIRNAME / "update-cache.json"

DEFAULT_UPDATE_PREFERENCES = {
    "enabled": True,
    "auto_check": True,
    "check_interval": 86400,
    "channel": "stable",
}


# Mirrored from manifest.OWNERSHIPS. Importing the manifest here would make the
# state module depend on the catalogue it is meant to outlive; the two are kept
# equal by `test_lifecycle_security.py`.
OWNERSHIPS = ("MANAGED_IMMUTABLE", "MANAGED_MUTABLE", "USER_DATA", "EXTERNAL_CONFIG")
MANAGED_KINDS = ("file", "external_block", "data_root")

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_DIGEST.match(value))


def _known(value: Any, allowed: tuple, fallback: str) -> str:
    """Keep a declared value, or fall back — never carry an unknown one."""

    return value if isinstance(value, str) and value in allowed else fallback


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class ManagedFile:
    """One path the stack owns, and the digest it had when the stack wrote it."""

    path: str                    # project-relative, POSIX separators
    component: str
    ownership: str
    digest_at_install: str | None = None
    created_by_ainative: bool = True
    kind: str = "file"           # "file" | "external_block" | "data_root"

    def to_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_record(cls, raw: Any) -> "ManagedFile":
        """Read one record, typing every field that gates a deletion.

        `bool(raw.get(...))` is not a type check: the string `"false"` is
        truthy, so a record saying the stack did not write a file was read as
        saying it did — and `uninstall` deleted the user's file (EMP-LC-029).
        Anything that is not the expected type falls to the value that
        preserves.
        """

        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise LifecycleError("INSTALL_STATE_CORRUPTED",
                                 "managed_files contains an entry without a path")
        created = raw.get("created_by_ainative", True)
        digest = raw.get("digest_at_install")
        return cls(
            path=raw["path"],
            component=str(raw.get("component", "")),
            ownership=_known(raw.get("ownership"), OWNERSHIPS, "MANAGED_MUTABLE"),
            # A digest that is not a digest cannot certify anything; `None`
            # classifies the file CONFLICT, which is never removed.
            digest_at_install=digest if _is_digest(digest) else None,
            # Not a bool: assume it is not ours, which is the safe direction.
            created_by_ainative=created if isinstance(created, bool) else False,
            kind=_known(raw.get("kind"), MANAGED_KINDS, "file"),
        )


def _update_preferences(raw: Any) -> dict:
    """Coerce the stored preferences, keeping the default for anything unusable.

    The state file is editable by hand, so its *values* are as untrusted as its
    keys. Copying a key through because its name was known let a
    `check_interval` of `"soon"` reach `int()` and take down `ainative status`
    with a traceback (EMP-LC-027). A preference that cannot be read is not an
    error — it is a preference we do not have.
    """

    preferences = dict(DEFAULT_UPDATE_PREFERENCES)
    if not isinstance(raw, dict):
        return preferences
    for key, default in DEFAULT_UPDATE_PREFERENCES.items():
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(default, bool):
            if isinstance(value, bool):
                preferences[key] = value
        elif isinstance(default, int):
            # `bool` is an `int` in Python; a boolean interval is not one.
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                preferences[key] = value
        elif isinstance(value, str) and value:
            preferences[key] = value
    return preferences


@dataclass
class InstallState:
    schema_version: int = SCHEMA_VERSION
    stack_version: str = "0.0.0"
    active_profile: str = "standard"
    previous_profile: str | None = None
    installation_id: str = field(default_factory=lambda: new_identifier("install"))
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    source_version: str = "0.0.0"
    source_revision: str | None = None
    installed_components: list[str] = field(default_factory=list)
    managed_files: list[ManagedFile] = field(default_factory=list)
    last_transaction: str | None = None
    update_channel: str = "stable"
    update_preferences: dict = field(default_factory=lambda: dict(DEFAULT_UPDATE_PREFERENCES))
    adopted_from_legacy: bool = False

    # --- queries ---------------------------------------------------------

    def file_for(self, path: str) -> ManagedFile | None:
        for entry in self.managed_files:
            if entry.path == path:
                return entry
        return None

    def files_for_component(self, component: str) -> list[ManagedFile]:
        return [entry for entry in self.managed_files if entry.component == component]

    def files_by_ownership(self, ownership: str) -> list[ManagedFile]:
        return [entry for entry in self.managed_files if entry.ownership == ownership]

    def replace_component_files(self, component: str, entries: Iterable[ManagedFile]) -> None:
        kept = [item for item in self.managed_files if item.component != component]
        kept.extend(entries)
        self.managed_files = sorted(kept, key=lambda item: (item.component, item.path))

    def drop_component(self, component: str) -> None:
        self.managed_files = [item for item in self.managed_files if item.component != component]
        self.installed_components = [item for item in self.installed_components if item != component]

    # --- serialisation ---------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["managed_files"] = [entry.to_record() for entry in
                                   sorted(self.managed_files,
                                          key=lambda item: (item.component, item.path))]
        record["installed_components"] = sorted(set(self.installed_components))
        return record

    @classmethod
    def from_record(cls, raw: Any) -> "InstallState":
        if not isinstance(raw, dict):
            raise LifecycleError("INSTALL_STATE_CORRUPTED", "state.json is not a JSON object")
        version = raw.get("schema_version")
        if not isinstance(version, int):
            raise LifecycleError("INSTALL_STATE_CORRUPTED", "state.json has no schema_version")
        if version > SCHEMA_VERSION:
            raise LifecycleError(
                "INSTALL_STATE_CORRUPTED",
                f"state.json schema_version {version} is newer than this release "
                f"understands ({SCHEMA_VERSION}); upgrade the CLI rather than downgrading state")
        profile = raw.get("active_profile")
        if not isinstance(profile, str) or not profile:
            raise LifecycleError("INSTALL_STATE_CORRUPTED", "state.json has no active_profile")
        components = raw.get("installed_components", [])
        if not isinstance(components, list) or not all(isinstance(i, str) for i in components):
            raise LifecycleError("INSTALL_STATE_CORRUPTED",
                                 "installed_components must be a list of strings")
        files = raw.get("managed_files", [])
        if not isinstance(files, list):
            raise LifecycleError("INSTALL_STATE_CORRUPTED", "managed_files must be a list")

        preferences = _update_preferences(raw.get("update_preferences"))

        return cls(
            schema_version=version,
            stack_version=str(raw.get("stack_version", "0.0.0")),
            active_profile=profile,
            previous_profile=raw.get("previous_profile"),
            installation_id=str(raw.get("installation_id") or new_identifier("install")),
            created_at=str(raw.get("created_at") or now()),
            updated_at=str(raw.get("updated_at") or now()),
            source_version=str(raw.get("source_version", "0.0.0")),
            source_revision=raw.get("source_revision"),
            installed_components=list(components),
            managed_files=[ManagedFile.from_record(item) for item in files],
            last_transaction=raw.get("last_transaction"),
            update_channel=str(raw.get("update_channel", "stable")),
            update_preferences=preferences,
            adopted_from_legacy=bool(raw.get("adopted_from_legacy", False)),
        )


def state_path(project: Path) -> Path:
    return project / STATE_RELATIVE


def exists(project: Path) -> bool:
    return state_path(project).is_file()


def load(project: Path) -> InstallState | None:
    """Read the state, or None when the project has never been installed into."""

    path = state_path(project)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LifecycleError("INSTALL_STATE_CORRUPTED",
                             f"cannot read {path}: {error}") from error
    return InstallState.from_record(payload)


def write_atomic(path: Path, payload: str) -> None:
    """Write via a same-directory temporary file and one rename.

    A partially-written state file is indistinguishable from a corrupt one, and
    this file is what every later operation trusts. `os.replace` is atomic on
    both POSIX and Windows when source and target share a directory.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                         dir=str(path.parent), prefix=".tmp-", delete=False)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    """Same guarantee as `write_atomic`, for content that is not text."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("wb", dir=str(path.parent), prefix=".tmp-", delete=False)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def save(project: Path, state: InstallState) -> Path:
    state.updated_at = now()
    path = state_path(project)
    write_atomic(path, json.dumps(state.to_record(), indent=2, sort_keys=True) + "\n")
    return path


def remove(project: Path) -> None:
    state_path(project).unlink(missing_ok=True)


__all__ = [
    "SCHEMA_VERSION", "LIFECYCLE_DIRNAME", "STATE_RELATIVE", "TRANSACTIONS_RELATIVE",
    "BACKUPS_RELATIVE", "UPDATE_CACHE_RELATIVE", "DEFAULT_UPDATE_PREFERENCES",
    "ManagedFile", "InstallState", "state_path", "exists", "load", "save", "remove",
    "write_atomic", "write_bytes_atomic", "now", "new_identifier",
    "OWNERSHIPS", "MANAGED_KINDS",
]
