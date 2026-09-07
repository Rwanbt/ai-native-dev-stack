"""Knowledge error codes (B1 foundation). Lifecycle-side only."""

from __future__ import annotations

from ainative.lifecycle.errors import EXIT_FAILED, EXIT_INVALID_REQUEST

ERROR_EXIT_CODES = {
    "KNOWLEDGE_MALFORMED": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_SCHEMA_UNKNOWN": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_IDENTITY_KEY_INVALID": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_ILLEGAL_STATE_TRANSITION": EXIT_INVALID_REQUEST,
    "KNOWLEDGE_GATE_CLOSED": EXIT_FAILED,
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


__all__ = ["ERROR_EXIT_CODES", "KnowledgeError"]
