"""Secret quarantine: fail-closed gate before untrusted persistence (B1 S11).

Pipeline position: size bound, then THIS gate (scanner availability,
secret scan), then source/path validation, envelope, persistence. The
builtin deterministic screen is always available and stays as defense
in depth; a stronger scanner is injected, never assumed. A required
scanner that is missing or crashing refuses persistence outright —
no silent fallback, and the refusal diagnostic names the class,
never the secret.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import KnowledgeError

_PATTERNS = (
    ("credential", re.compile(r"(?i)\b(api[_-]?key|client[_-]?secret|"
                              r"secret[_-]?key|auth[_-]?token|access[_-]?token|"
                              r"password|passwd|bearer)\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")),
)


def builtin_screen(text: str) -> str | None:
    """Deterministic pattern screen. Always available. Pure function."""

    if not isinstance(text, str):
        return None
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            return label
    return None


def check(*texts: Any, purpose: str, scanner: Any = None) -> None:
    """Refuse secret-bearing input before persistence. Fail closed.

    `scanner` is an injected stronger scanner exposing `available`
    (bool attribute, not a method) and `scan(text)` (label or None).
    When one is required but
    missing, or when it errors, persistence is refused — the builtin
    screen never silently stands in for a required scanner, and no
    fallback path writes.
    """

    if scanner is not None:
        try:
            available = bool(scanner.available)
        except Exception as error:
            raise KnowledgeError("KNOWLEDGE_SECRET_SCANNER_UNAVAILABLE",
                                 f"{purpose}: scanner availability failed") from error
        if not available:
            raise KnowledgeError("KNOWLEDGE_SECRET_SCANNER_UNAVAILABLE",
                                 f"{purpose}: required scanner unavailable")
        try:
            hits = [scanner.scan(text) for text in texts
                    if isinstance(text, str)]
        except Exception as error:
            raise KnowledgeError("KNOWLEDGE_SECRET_SCANNER_UNAVAILABLE",
                                 f"{purpose}: scanner errored, failing closed") from error
        if any(hits):
            raise KnowledgeError("KNOWLEDGE_SECRET_REFUSED",
                                 f"{purpose}: secret-bearing input refused")
    for text in texts:
        if isinstance(text, str) and builtin_screen(text) is not None:
            raise KnowledgeError("KNOWLEDGE_SECRET_REFUSED",
                                 f"{purpose}: secret-bearing input refused")


__all__ = ["builtin_screen", "check"]
