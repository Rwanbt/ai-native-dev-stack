"""PR-02 filesystem Work Controller with manifest-last commits."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
import secrets
import shutil
import socket
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .contracts import NORMATIVE_ARTIFACTS, ContractError, validate_normative, canonical_json_bytes, canonical_path, digest_bytes, generate_uid, validate_artifact


class ControllerError(RuntimeError):
    """A failed controller operation; committed state remains authoritative."""


def process_is_alive(pid: int) -> bool:
    """Report whether a PID is running on this host.

    WHY: a recycled PID reads as alive and a permission error reads as alive.
    Both err toward refusing to reclaim a lock, which is the fail-closed side.
    """

    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    query_limited_information = 0x1000
    still_active = 259
    # WHY declare the signatures: without them ctypes marshals the returned
    # HANDLE as a 32-bit int, so a live process reads as dead and its lock
    # would be reclaimed underneath it.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class WorkController:
    """Sole normative writer for one work directory."""

    def __init__(self, work_dir: str | os.PathLike[str], *, failure_injector: Callable[[str], None] | None = None):
        self.root = Path(work_dir)
        self.manifest_path = self.root / "manifest.json"
        self.revisions = self.root / "revisions"
        self.staging = self.root / ".staging"
        self.lock_path = self.root / ".controller.lock"
        self.failure_injector = failure_injector

    def _step(self, name: str) -> None:
        if self.failure_injector:
            self.failure_injector(name)

    def _lock(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            return self._acquire()
        except FileExistsError:
            pass
        if not self._reclaim_dead_lock():
            raise ControllerError("CONCURRENT_WRITER")
        try:
            return self._acquire()
        except FileExistsError as exc:
            raise ControllerError("CONCURRENT_WRITER") from exc

    def _acquire(self) -> int:
        handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        owner = {"pid": os.getpid(), "host": socket.gethostname(), "created_at": datetime.now(timezone.utc).isoformat(), "transaction_id": uuid.uuid4().hex}
        os.write(handle, canonical_json_bytes(owner))
        return handle

    def _reclaim_dead_lock(self) -> bool:
        """Reclaim only a lock this host owns whose writer no longer exists."""

        try:
            owner = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(owner["pid"])
            host = owner["host"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ControllerError("INVALID_LOCK") from exc
        # WHY: a writer on another machine cannot be observed from here, so age
        # alone never justifies breaking its lock.
        if host != socket.gethostname() or process_is_alive(pid):
            return False
        self.lock_path.unlink(missing_ok=True)
        return True

    def _unlock(self, handle: int) -> None:
        os.close(handle)
        self.lock_path.unlink(missing_ok=True)

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            raise ControllerError("NO_COMMITTED_STATE")
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            from .contracts import validate_artifact
            validate_artifact(manifest)
            self._validate_pointers(manifest)
            return manifest
        except (OSError, json.JSONDecodeError, ContractError) as exc:
            raise ControllerError("INVALID_COMMITTED_STATE") from exc

    def _validate_pointers(self, manifest: Mapping[str, Any]) -> None:
        for pointer in manifest["artifacts"].values():
            path = self.root / canonical_path(pointer["path"])
            if not path.is_file() or digest_bytes(path.read_bytes()) != pointer["digest"]:
                raise ControllerError("UNEXPECTED_MUTATION")

    def read(self) -> dict[str, Any]:
        return self._load_manifest()

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))
        try:
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        except OSError:
            pass

    def _commit(self, previous: dict[str, Any] | None, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        revision = 1 if previous is None else previous["revision"] + 1
        transaction = uuid.uuid4().hex
        stage = self.staging / transaction
        revision_dir = self.revisions / str(revision)
        stage.mkdir(parents=True)
        try:
            self._step("before_artifact_write")
            pointers: dict[str, dict[str, str]] = {}
            for name, value in artifacts.items():
                if not isinstance(name, str) or not name:
                    raise ControllerError("INVALID_ARTIFACT_NAME")
                normative = name in NORMATIVE_ARTIFACTS
                if normative:
                    try:
                        validate_normative(name, value)
                    except ContractError as error:
                        raise ControllerError(f"INVALID_NORMATIVE_ARTIFACT:{name}:{error.code}") from error
                elif isinstance(value, Mapping) and "schema_name" in value:
                    validate_artifact(value)
                filename = f"{name}.json"
                staged = stage / filename
                self._write_json(staged, value)
                pointers[name] = {"path": f"revisions/{revision}/{filename}", "digest": digest_bytes(staged.read_bytes()), "normative": normative}
                self._step("after_staged_file")
            revision_dir.parent.mkdir(parents=True, exist_ok=True)
            if revision_dir.exists():
                raise ControllerError("REVISION_ALREADY_EXISTS")
            shutil.move(str(stage), str(revision_dir))
            self._step("after_promotion_before_manifest")
            manifest = {"schema_name": "work_manifest", "schema_version": 1, "work_uid": previous["work_uid"] if previous else generate_uid("work"), "revision": revision, "artifacts": pointers}
            temporary = self.root / f".manifest.{secrets.token_hex(8)}.tmp"
            self._write_json(temporary, manifest)
            self._step("before_manifest_replace")
            os.replace(temporary, self.manifest_path)
            self._step("after_manifest_commit")
            return manifest
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    def create(self, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        handle = self._lock()
        try:
            self._recover_interrupted()
            if self.manifest_path.exists():
                raise ControllerError("WORK_ALREADY_EXISTS")
            return self._commit(None, artifacts)
        finally:
            self._unlock(handle)

    def mutate(self, expected_revision: int, set_artifacts: Mapping[str, Any] | None = None, *, delete_artifacts: Iterable[str] = ()) -> dict[str, Any]:
        """Apply an explicit change to the committed set.

        @contract Nothing disappears unless it is named in delete_artifacts.
        A revision is the previous set with the named artifacts replaced and
        the named artifacts removed, never only what the caller supplied.
        """

        handle = self._lock()
        try:
            self._recover_interrupted()
            current = self._load_manifest()
            if expected_revision != current["revision"]:
                raise ControllerError("STALE_REVISION")
            merged = self._read_artifacts(current)
            for name in delete_artifacts:
                if name not in merged:
                    raise ControllerError(f"UNKNOWN_ARTIFACT:{name}")
                del merged[name]
            merged.update(set_artifacts or {})
            if not merged:
                raise ControllerError("EMPTY_REVISION")
            return self._commit(current, merged)
        finally:
            self._unlock(handle)

    def _read_artifacts(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Load the artifacts a validated manifest points at."""

        artifacts: dict[str, Any] = {}
        for name, pointer in manifest["artifacts"].items():
            path = self.root / canonical_path(pointer["path"])
            try:
                artifacts[name] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ControllerError("INVALID_COMMITTED_STATE") from error
        return artifacts

    def load_committed_artifacts(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return the validated manifest and the exact committed artifact set.

        @contract Every pointer is digest-checked before its artifact is read,
        and every normative artifact is validated against its schema, so a
        caller cannot receive committed state the controller would refuse to
        write today.
        """

        manifest = self._load_manifest()
        artifacts = self._read_artifacts(manifest)
        for name, value in artifacts.items():
            if name in NORMATIVE_ARTIFACTS:
                try:
                    validate_normative(name, value)
                except ContractError as error:
                    raise ControllerError(f"INVALID_NORMATIVE_ARTIFACT:{name}:{error.code}") from error
        return manifest, artifacts

    def recover_staging(self) -> int:
        handle = self._lock()
        try:
            return self._recover_interrupted()
        finally:
            self._unlock(handle)

    def _recover_interrupted(self) -> int:
        """Discard files that cannot be authoritative without a matching manifest."""

        removed = 0
        if self.staging.exists():
            for child in self.staging.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                    removed += 1
        for temporary in self.root.glob(".manifest.*.tmp"):
            temporary.unlink(missing_ok=True)
            removed += 1
        committed_revision = 0
        if self.manifest_path.exists():
            committed_revision = self._load_manifest()["revision"]
        if self.revisions.exists():
            for child in self.revisions.iterdir():
                if child.is_dir() and child.name.isdigit() and int(child.name) > committed_revision:
                    shutil.rmtree(child)
                    removed += 1
        return removed
