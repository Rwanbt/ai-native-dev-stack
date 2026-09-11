"""Atomic local operator authority store; repository files never grant bindings."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
import tempfile
from typing import Any


class AuthorityStoreCorruptError(ValueError):
    """Raised when the authority store cannot be read as a supported generation."""


class AuthorityStore:
    def __init__(self, path: Path):
        self.path = path

    def _backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    def bindings(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists(): return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AuthorityStoreCorruptError(f"authority store is unreadable or corrupt: {self.path}") from error
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise AuthorityStoreCorruptError(f"authority store has an unsupported schema: {self.path}")
        bindings = payload.get("bindings", {})
        if not isinstance(bindings, dict):
            raise AuthorityStoreCorruptError(f"authority store bindings are malformed: {self.path}")
        return dict(bindings)

    def binding(self, domain: str) -> dict[str, Any] | None: return self.bindings().get(domain)

    def replace(self, bindings: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"schema_version": 1, "bindings": bindings}, sort_keys=True, separators=(",", ":"))
        if self.path.exists():
            shutil.copy2(self.path, self._backup_path())
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as file:
            file.write(payload); temporary = Path(file.name)
        temporary.replace(self.path)

    def restore_from_backup(self) -> bool:
        backup = self._backup_path()
        if not backup.exists():
            return False
        content = backup.read_bytes()
        with tempfile.NamedTemporaryFile("wb", dir=self.path.parent, delete=False) as file:
            file.write(content); temporary = Path(file.name)
        temporary.replace(self.path)
        return True