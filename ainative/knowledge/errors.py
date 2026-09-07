"""Knowledge error codes. Lifecycle-side only; never verdict authority.

Exit codes reuse `ainative.lifecycle.errors` values so the future
`ainative knowledge` CLI speaks the same contract, but no authority
module is imported here (ADR-0011 section 2).
"""

from __future__ import annotations

from ainative.lifecycle.errors import (
    EXIT_FAILED,
    EXIT_INVALID_REQUEST,
    EXIT_OK,
    EXIT_RECOVERY_REQUIRED,
)

__all__ = ["EXIT_OK", "EXIT_FAILED", "EXIT_INVALID_REQUEST", "EXIT_RECOVERY_REQUIRED"]

ERROR_EXIT_CODES = {
    "KNOWLEDGE_SCHEMA_UNKNOWN": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_MALFORMED": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_BAD_STATUS": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_BAD_TRANSITION": EXIT_FAILED,
    "KNOWLEDGE_BAD_LOCATOR": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_SECRET_REJECTED": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_TARGET_UNSUPPORTED": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_CONFIRMATION_REQUIRED": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_DUPLICATE_ID": EXIT_FAILED,
    "KNOWLEDGE_NOT_FOUND": EXIT_FAILED,
    "KNOWLEDGE_CONFLICT": EXIT_FAILED,
    "KNOWLEDGE_STORE_CORRUPTED": EXIT_FAILED,
    "KNOWLEDGE_STALE_BASE": EXIT_FAILED,
    "KNOWLEDGE_PROMOTION_CONFLICT": EXIT_FAILED,
}


class KnowledgeError(Exception):
    """A refusal carrying a stable code, a message, and optional detail."""

    def __init__(self, code: str, message: str, **detail: object) -> None:
        if code not in ERROR_EXIT_CODES:
            raise KeyError(f"undeclared knowledge error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = dict(detail)

    @property
    def exit_code(self) -> int:
        return ERROR_EXIT_CODES[self.code]

    def to_record(self) -> dict:
        return {"error": self.code, "message": self.message, "detail": self.detail}

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


__all__ += ["ERROR_EXIT_CODES", "KnowledgeError"]