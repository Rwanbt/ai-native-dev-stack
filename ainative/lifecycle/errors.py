"""Stable lifecycle error codes and their process exit codes.

A user reads a code, not a traceback. A script reads an exit code, not a
message. Both are part of the CLI's contract, so both live here rather than
being spelled out at each raise site.
"""

from __future__ import annotations

# Exit codes. Documented in docs/DISTRIBUTION-LIFECYCLE.md and asserted by the
# CLI tests; changing one is a breaking change to every script that calls us.
EXIT_OK = 0
EXIT_FAILED = 1          # the operation ran and did not succeed / state unhealthy
EXIT_INVALID_REQUEST = 2  # the request or configuration is wrong
EXIT_RECOVERY_REQUIRED = 3  # an interrupted transaction must be repaired first

# Every code the lifecycle layer can refuse with, and the exit code it maps to.
# `PROFILE_INVALID` and friends are what the user sees; the message that follows
# is free text and never load-bearing.
ERROR_EXIT_CODES = {
    "PROFILE_INVALID": EXIT_INVALID_REQUEST,
    "COMPONENT_UNKNOWN": EXIT_INVALID_REQUEST,
    "MANIFEST_INVALID": EXIT_INVALID_REQUEST,
    "DISTRIBUTION_SOURCE_UNAVAILABLE": EXIT_INVALID_REQUEST,
    "PROJECT_ROOT_INVALID": EXIT_INVALID_REQUEST,
    "CONFIRMATION_REQUIRED": EXIT_INVALID_REQUEST,
    "PATH_ESCAPE": EXIT_INVALID_REQUEST,
    "INSTALL_STATE_CORRUPTED": EXIT_FAILED,
    "NOT_INSTALLED": EXIT_FAILED,
    "USER_MODIFIED_CONFLICT": EXIT_FAILED,
    "TRANSACTION_IN_PROGRESS": EXIT_RECOVERY_REQUIRED,
    "RECOVERY_REQUIRED": EXIT_RECOVERY_REQUIRED,
    "LOCK_HELD": EXIT_FAILED,
    "UPDATE_UNAVAILABLE": EXIT_FAILED,
    "UPDATE_CHECK_FAILED": EXIT_FAILED,
    "UPDATE_INTEGRITY_FAILED": EXIT_FAILED,
    "ROLLBACK_UNAVAILABLE": EXIT_FAILED,
    "APPLY_FAILED": EXIT_FAILED,
}


class LifecycleError(Exception):
    """A refusal carrying a stable code, a message, and optional detail."""

    def __init__(self, code: str, message: str, **detail: object) -> None:
        if code not in ERROR_EXIT_CODES:
            # An unlisted code would exit with an undocumented status. Fail
            # loudly here rather than shipping a code no caller can handle.
            raise KeyError(f"undeclared lifecycle error code: {code}")
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


__all__ = [
    "EXIT_OK",
    "EXIT_FAILED",
    "EXIT_INVALID_REQUEST",
    "EXIT_RECOVERY_REQUIRED",
    "ERROR_EXIT_CODES",
    "LifecycleError",
]
