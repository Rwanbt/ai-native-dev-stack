"""Validated, bound verification evidence.

This module is the sole runtime representation accepted by convergence.  It
wraps the normative ``verification_run`` artifact instead of letting process
results or arbitrary mappings acquire verdict authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

from .contracts import ContractError, generate_uid, validate_artifact


@dataclass(frozen=True)
class VerificationEvidence:
    """An immutable ``verification_run`` artifact validated at construction."""

    artifact: Mapping[str, Any]

    def __post_init__(self) -> None:
        try:
            validate_artifact(self.artifact)
        except ContractError as exc:
            raise EvidenceError(exc.code) from exc

    @property
    def uid(self) -> str:
        return str(self.artifact["uid"])

    @property
    def result(self) -> str:
        return str(self.artifact["result"])

    @property
    def verification_specification_uid(self) -> str:
        return str(self.artifact["verification_specification"]["uid"])

    def to_record(self) -> dict[str, Any]:
        return dict(self.artifact)


class EvidenceError(RuntimeError):
    """A runtime evidence record was absent, malformed, or unbound."""


def build_verification_evidence(
    binding: Mapping[str, Any],
    *,
    command: str,
    result: str,
    exit_code: int | None,
    stdout: bytes,
    stderr: bytes,
    duration_ms: int,
    substance_metadata: Mapping[str, Any],
    started_at: str | None = None,
) -> VerificationEvidence:
    """Bind one process observation to caller-supplied normative identities.

    @contract `started_at` is when the process began, observed by the caller
    that started it. Stamping it here instead would put both ends of the
    execution window at record-build time, describing a run of zero duration
    however long it took. Absent, it degrades to the record time rather than
    inventing a window.
    """

    record = dict(binding)
    finished = datetime.now(timezone.utc).isoformat()
    record.update(
        {
            "schema_name": "verification_run",
            "schema_version": 1,
            "uid": generate_uid("run"),
            "command": command,
            "result": result,
            "exit_code": exit_code,
            "started_at": started_at or finished,
            "finished_at": finished,
            "duration_ms": duration_ms,
            "stdout_digest": sha256(stdout).hexdigest(),
            "stderr_digest": sha256(stderr).hexdigest(),
            "substance_metadata": dict(substance_metadata),
        }
    )
    return VerificationEvidence(record)
