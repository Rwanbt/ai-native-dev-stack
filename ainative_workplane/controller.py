"""PR-02 filesystem Work Controller with manifest-last commits."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import ContractError, canonical_json_bytes, canonical_path, digest_bytes, generate_uid, validate_artifact


class ControllerError(RuntimeError):
    """A failed controller operation; committed state remains authoritative."""


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

    def _lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ControllerError("CONCURRENT_WRITER") from exc
        return handle

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
                if isinstance(value, Mapping) and "schema_name" in value:
                    validate_artifact(value)
                filename = f"{name}.json"
                staged = stage / filename
                self._write_json(staged, value)
                pointers[name] = {"path": f"revisions/{revision}/{filename}", "digest": digest_bytes(staged.read_bytes())}
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

    def mutate(self, expected_revision: int, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        handle = self._lock()
        try:
            self._recover_interrupted()
            current = self._load_manifest()
            if expected_revision != current["revision"]:
                raise ControllerError("STALE_REVISION")
            return self._commit(current, artifacts)
        finally:
            self._unlock(handle)

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
