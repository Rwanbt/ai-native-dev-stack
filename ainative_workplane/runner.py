"""PR-04 constrained argv verification runner."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import ContractError, canonical_digest, generate_uid


@dataclass(frozen=True)
class RunResult:
    uid: str
    command: str
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    evidence_provenance: str


class RunnerError(RuntimeError):
    pass


_SECRET = re.compile(r"(?i)(token|secret|password|api[_-]?key)=([^\s]+)")


def load_registry(registry: Mapping[str, Any], expected_digest: str | None = None) -> dict[str, Any]:
    if registry.get("schema_name") != "command_registry" or registry.get("schema_version") != 1:
        raise RunnerError("UNSUPPORTED_SCHEMA_VERSION")
    commands = registry.get("commands")
    if not isinstance(commands, Mapping) or not commands:
        raise RunnerError("INVALID_COMMAND_REGISTRY")
    for name, definition in commands.items():
        if not isinstance(name, str) or not isinstance(definition, Mapping) or not isinstance(definition.get("argv"), list):
            raise RunnerError("INVALID_COMMAND_REGISTRY")
        if not definition["argv"] or not all(isinstance(arg, str) for arg in definition["argv"]):
            raise RunnerError("INVALID_COMMAND_REGISTRY")
        if definition.get("shell", False):
            raise RunnerError("SHELL_COMMAND_FORBIDDEN")
        if not isinstance(definition.get("timeout_seconds", 30), int) or definition.get("timeout_seconds", 30) < 1:
            raise RunnerError("INVALID_COMMAND_REGISTRY")
        if not isinstance(definition.get("max_output_bytes", 1_000_000), int) or definition.get("max_output_bytes", 1_000_000) < 1:
            raise RunnerError("INVALID_COMMAND_REGISTRY")
    if expected_digest is not None and canonical_digest(registry) != expected_digest:
        raise RunnerError("COMMAND_REGISTRY_CHANGED")
    return dict(registry)


class VerificationRunner:
    def __init__(self, registry: Mapping[str, Any], *, provenance: str = "GIT_REVIEWED", runs_dir: str | Path | None = None):
        self.registry = load_registry(registry)
        self.provenance = provenance
        self.runs_dir = Path(runs_dir) if runs_dir else None

    def run(self, command: str, *, cwd: str | Path, require_substance: bool = False) -> RunResult:
        definition = self.registry["commands"].get(command)
        if definition is None:
            raise RunnerError("UNKNOWN_COMMAND")
        started = time.monotonic()
        try:
            completed = subprocess.run(definition["argv"], cwd=cwd, shell=False, capture_output=True, timeout=definition.get("timeout_seconds", 30), check=False)
            stdout_bytes, stderr_bytes = completed.stdout, completed.stderr
            if len(stdout_bytes) + len(stderr_bytes) > definition.get("max_output_bytes", 1_000_000):
                raise RunnerError("OUTPUT_LIMIT_EXCEEDED")
            stdout = _SECRET.sub(r"\1=[REDACTED]", stdout_bytes.decode("utf-8", errors="replace"))
            stderr = _SECRET.sub(r"\1=[REDACTED]", stderr_bytes.decode("utf-8", errors="replace"))
            status = "PASS" if completed.returncode == 0 else "FAIL"
            if require_substance and completed.returncode == 0 and not (stdout.strip() or stderr.strip()):
                status = "SUSPICIOUS_VERIFICATION"
            result = RunResult(generate_uid("run"), command, status, completed.returncode, stdout, stderr, int((time.monotonic() - started) * 1000), self.provenance)
        except subprocess.TimeoutExpired:
            result = RunResult(generate_uid("run"), command, "TIMEOUT", None, "", "", int((time.monotonic() - started) * 1000), self.provenance)
        if self.runs_dir:
            self.runs_dir.mkdir(parents=True, exist_ok=True)
            path = self.runs_dir / f"{result.uid}.json"
            path.write_text(json.dumps(result.__dict__, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return result
