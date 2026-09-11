"""Atomic local operator authority store; repository files never grant bindings."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile

class AuthorityStore:
    def __init__(self, path: Path): self.path = path
    def bindings(self) -> dict[str, dict[str, str]]:
        if not self.path.exists(): return {}
        payload=json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1: raise ValueError("unsupported authority schema")
        return dict(payload.get("bindings", {}))
    def binding(self, domain: str) -> dict[str, str] | None: return self.bindings().get(domain)
    def replace(self, bindings: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload=json.dumps({"schema_version":1,"bindings":bindings},sort_keys=True,separators=(",",":"))
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=self.path.parent,delete=False) as file:
            file.write(payload); temporary=Path(file.name)
        temporary.replace(self.path)
