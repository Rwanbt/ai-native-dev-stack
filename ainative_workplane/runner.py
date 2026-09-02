"""PR-04 constrained argv verification runner."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from queue import Empty, Queue
from threading import Thread
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import canonical_digest
from .evidence import VerificationEvidence, build_verification_evidence


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
        try:
            completed, stdout_bytes, stderr_bytes = self._run_bounded(definition, cwd)
            stdout = _SECRET.sub(r"\1=[REDACTED]", stdout_bytes.decode("utf-8", errors="replace"))
            stderr = _SECRET.sub(r"\1=[REDACTED]", stderr_bytes.decode("utf-8", errors="replace"))
            status = "PASS" if completed.returncode == 0 else "FAIL"
            if require_substance and completed.returncode == 0 and not (stdout.strip() or stderr.strip()):
                status = "SUSPICIOUS_VERIFICATION"
            result = build_verification_evidence(binding, command=command, result=status, exit_code=completed.returncode, stdout=stdout_bytes, stderr=stderr_bytes, duration_ms=int((time.monotonic() - started) * 1000), substance_metadata={"stdout_preview": stdout, "stderr_preview": stderr})
        except subprocess.TimeoutExpired:
            result = build_verification_evidence(binding, command=command, result="TIMEOUT", exit_code=None, stdout=b"", stderr=b"", duration_ms=int((time.monotonic() - started) * 1000), substance_metadata={})
        if self.runs_dir:
            self.runs_dir.mkdir(parents=True, exist_ok=True)
            path = self.runs_dir / f"{result.uid}.json"
            path.write_text(json.dumps(result.to_record(), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return result

    def _run_bounded(self, definition: Mapping[str, Any], cwd: str | Path) -> tuple[subprocess.Popen[bytes], bytes, bytes]:
        process = subprocess.Popen(
            definition["argv"],
            cwd=cwd,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        queue: Queue[tuple[str, bytes]] = Queue()

        def drain(name: str, stream: Any) -> None:
            try:
                while chunk := stream.read(8192):
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
                self._terminate_process_tree(process)
                raise subprocess.TimeoutExpired(definition["argv"], definition.get("timeout_seconds", 30))
            try:
                name, chunk = queue.get(timeout=0.02)
            except Empty:
                continue
            if len(output["stdout"]) + len(output["stderr"]) + len(chunk) > limit:
                self._terminate_process_tree(process)
                raise RunnerError("OUTPUT_LIMIT_EXCEEDED")
            output[name].extend(chunk)
        process.wait()
        return process, bytes(output["stdout"]), bytes(output["stderr"])

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
        """Terminate the isolated command group so children cannot outlive evidence."""

        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        else:
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
