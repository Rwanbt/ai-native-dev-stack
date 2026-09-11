"""Metadata-only audit records (Multi-Vault plan section 17).

Allowed: timestamps, domain/operation/decision/reason codes, harness/provider
metadata, stable ids, digests and qualification levels. Forbidden: prompts,
vault content, secrets, tokens, API keys, private file content and raw
RuntimeContextHandle material. Values are short single-line metadata; anything
that cannot be expressed that way is rejected, never truncated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path

QUALIFICATION_LEVELS = ("", "UNKNOWN", "GUARDED", "ENFORCED-DIAGNOSTIC", "ENFORCED-AUTHENTICATED")
MAX_FIELD_LENGTH = 200


@dataclass(frozen=True)
class AuditRecord:
    timestamp: str
    security_domain_id: str
    operation: str
    decision: str
    reason_code: str
    harness: str = ""
    provider_class: str = ""
    model_identifier: str = ""
    remote_stable_id: str = ""
    transport_digest: str = ""
    revocation_cause: str = ""
    qualification_level: str = ""

    def validate(self) -> None:
        if not self.timestamp or not self.security_domain_id or not self.operation or not self.decision or not self.reason_code:
            raise ValueError("audit record requires timestamp, domain, operation, decision and reason code")
        if self.qualification_level not in QUALIFICATION_LEVELS:
            raise ValueError("audit record carries an unsupported qualification level")
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, str):
                raise ValueError(f"audit field {field.name} must be a string")
            if len(value) > MAX_FIELD_LENGTH or "\n" in value or "\r" in value:
                raise ValueError(f"audit field {field.name} is not single-line metadata")

    def encode(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


class AuditLog:
    """Append-only JSON-lines log; audit is not an authorization source."""

    def __init__(self, path: Path):
        self.path = path

    def append(self, record: AuditRecord) -> None:
        record.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(record.encode() + "\n")

    def query(self, *, security_domain_id: str | None = None, decision: str | None = None, reason_code: str | None = None) -> tuple[AuditRecord, ...]:
        if not self.path.exists():
            return ()
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            record = AuditRecord(**data)
            record.validate()
            if security_domain_id is not None and record.security_domain_id != security_domain_id:
                continue
            if decision is not None and record.decision != decision:
                continue
            if reason_code is not None and record.reason_code != reason_code:
                continue
            records.append(record)
        return tuple(records)