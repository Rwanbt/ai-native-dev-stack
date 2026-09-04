"""PR-04 constrained argv verification runner."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Thread
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import ContractError, canonical_digest, validate_artifact
from .evidence import VerificationEvidence, build_verification_evidence
from .isolation import IsolatedProcess, spawn
from .substance import evaluate as evaluate_substance


class RunnerError(RuntimeError):
    pass


# Defense in depth, not perfect secret detection: persisted evidence keeps
# digests and a bounded preview rather than the full log, so a miss here is
# not a full disclosure.
_REDACTIONS = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"(?i)\b(authorization)\s*:\s*(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), r"\1: \2 [REDACTED]"),
    (re.compile(r"(?i)\b(set-cookie|cookie)\s*:\s*[^\r\n]+"), r"\1: [REDACTED]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"(?i)\b(aws_secret_access_key|secret|token|password|passwd|api[_-]?key)\b\"?\s*[=:]\s*\"?[^\s\"',]+"), r"\1=[REDACTED]"),
)

PREVIEW_CHARS = 512
READ_CHUNK = 8192


def redact(text: str) -> str:
    """Mask the credential shapes a verification command most often prints."""

    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def load_registry(registry: Mapping[str, Any], expected_digest: str | None = None) -> dict[str, Any]:
    """Load a registry, refusing exactly what the contract refuses.

    @contract The validator is the one in contracts.py, so a registry the
    controller commits can never be one the runner rejects.
    """

    try:
        validate_artifact(registry)
    except ContractError as error:
        raise RunnerError(error.code) from error
    if expected_digest is not None and canonical_digest(registry) != expected_digest:
        raise RunnerError("COMMAND_REGISTRY_CHANGED")
    return dict(registry)


class VerificationRunner:
    def __init__(self, registry: Mapping[str, Any], *, runs_dir: str | Path | None = None):
        self.registry = load_registry(registry)
        self.runs_dir = Path(runs_dir) if runs_dir else None

    def run(self, command: str, *, cwd: str | Path, binding: Mapping[str, Any], require_substance: bool = False) -> VerificationEvidence:
        definition = self.registry["commands"].get(command)
        if definition is None:
            raise RunnerError("UNKNOWN_COMMAND")
        if binding.get("command_registry_digest") != canonical_digest(self.registry):
            raise RunnerError("COMMAND_REGISTRY_BINDING_MISMATCH")
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            completed, stdout_bytes, stderr_bytes = self._run_bounded(definition, cwd)
            stdout = redact(stdout_bytes.decode("utf-8", errors="replace"))
            stderr = redact(stderr_bytes.decode("utf-8", errors="replace"))
            status = "PASS" if completed.returncode == 0 else "FAIL"
            suspicious, observed = evaluate_substance(definition.get("substance"), stdout=stdout, stderr=stderr, exit_code=completed.returncode)
            if require_substance and completed.returncode == 0 and suspicious:
                status = "SUSPICIOUS_VERIFICATION"
            metadata = {**observed, "stdout_preview": stdout[:PREVIEW_CHARS], "stderr_preview": stderr[:PREVIEW_CHARS]}
            result = build_verification_evidence(binding, command=command, result=status, exit_code=completed.returncode, stdout=stdout_bytes, stderr=stderr_bytes, duration_ms=int((time.monotonic() - started) * 1000), substance_metadata=metadata, started_at=started_at)
        except subprocess.TimeoutExpired:
            result = build_verification_evidence(binding, command=command, result="TIMEOUT", exit_code=None, stdout=b"", stderr=b"", duration_ms=int((time.monotonic() - started) * 1000), substance_metadata={}, started_at=started_at)
        if self.runs_dir:
            self.runs_dir.mkdir(parents=True, exist_ok=True)
            path = self.runs_dir / f"{result.uid}.json"
            path.write_text(json.dumps(result.to_record(), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return result

    def _run_bounded(self, definition: Mapping[str, Any], cwd: str | Path) -> tuple[subprocess.Popen[bytes], bytes, bytes]:
        try:
            isolated = spawn(definition["argv"], cwd)
        except OSError as error:
            # A command the operating system refuses to start is a registry
            # fact, not evidence about the work under verification.
            raise RunnerError("COMMAND_NOT_EXECUTABLE") from error
        try:
            return self._collect(isolated, definition)
        finally:
            isolated.close()

    def _collect(self, isolated: IsolatedProcess, definition: Mapping[str, Any]) -> tuple[subprocess.Popen[bytes], bytes, bytes]:
        process = isolated.process
        queue: Queue[tuple[str, bytes]] = Queue()

        def drain(name: str, stream: Any) -> None:
            try:
                # read1, not read: read blocks until the full buffer is filled,
                # so a command that prints under one buffer and then keeps
                # running would defeat the output bound entirely.
                while chunk := stream.read1(READ_CHUNK):
                    queue.put((name, chunk))
            finally:
                stream.close()

        threads = [Thread(target=drain, args=("stdout", process.stdout), daemon=True), Thread(target=drain, args=("stderr", process.stderr), daemon=True)]
        for thread in threads:
            thread.start()
        output = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + definition.get("timeout_seconds", 30)
        limit = definition.get("max_output_bytes", 1_000_000)
        while any(thread.is_alive() for thread in threads) or not queue.empty():
            if time.monotonic() >= deadline:
                isolated.terminate_tree()
                raise subprocess.TimeoutExpired(definition["argv"], definition.get("timeout_seconds", 30))
            try:
                name, chunk = queue.get(timeout=0.02)
            except Empty:
                continue
            if len(output["stdout"]) + len(output["stderr"]) + len(chunk) > limit:
                isolated.terminate_tree()
                raise RunnerError("OUTPUT_LIMIT_EXCEEDED")
            output[name].extend(chunk)
        process.wait()
        return process, bytes(output["stdout"]), bytes(output["stderr"])
