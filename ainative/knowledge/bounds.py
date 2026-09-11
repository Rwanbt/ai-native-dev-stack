"""Storage bounds (B1 S12). Configurable, deterministic, refused loudly."""

from __future__ import annotations

from dataclasses import dataclass

MAX_CANDIDATE_PAYLOAD = 16 * 1024
MAX_SUPPORT_PAYLOAD = 8 * 1024
MAX_CANDIDATE_COUNT = 10000
MAX_AUDIT_COUNT = 50000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
RETENTION_DAYS = 90
WARNING_THRESHOLD = 0.8


@dataclass(frozen=True)
class Bounds:
    max_candidate_payload: int = MAX_CANDIDATE_PAYLOAD
    max_support_payload: int = MAX_SUPPORT_PAYLOAD
    max_candidate_count: int = MAX_CANDIDATE_COUNT
    max_audit_count: int = MAX_AUDIT_COUNT
    max_total_bytes: int = MAX_TOTAL_BYTES
    retention_days: int = RETENTION_DAYS
    warning_threshold: float = WARNING_THRESHOLD


__all__ = ["MAX_CANDIDATE_PAYLOAD", "MAX_SUPPORT_PAYLOAD",
           "MAX_CANDIDATE_COUNT", "MAX_AUDIT_COUNT", "MAX_TOTAL_BYTES",
           "RETENTION_DAYS", "WARNING_THRESHOLD", "Bounds"]
