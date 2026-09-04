"""Content digests, and the four states a managed file can be in.

Ownership without a digest is a list of filenames, and a list of filenames
cannot tell a file the stack wrote from a file the user rewrote. Every managed
path therefore carries the SHA-256 it had when the stack wrote it, and every
destructive decision is taken by comparing that value with the bytes on disk.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

# The four classifications every managed file resolves to.
UNCHANGED = "UNCHANGED"
USER_MODIFIED = "USER_MODIFIED"
MISSING = "MISSING"
CONFLICT = "CONFLICT"

_READ_CHUNK = 1 << 16


def digest_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def digest_file(path: Path) -> str | None:
    """SHA-256 of a regular file, or None when it is absent or not a file.

    A symlink is deliberately not followed for classification: a managed path
    replaced by a link is not the file we wrote, and reporting the target's
    digest would let it pass as `UNCHANGED`.
    """

    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as handle:
            hasher = sha256()
            while True:
                chunk = handle.read(_READ_CHUNK)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def classify(path: Path, digest_at_install: str | None) -> str:
    """Compare a managed path against the digest recorded when it was written.

    `CONFLICT` is reserved for the case where the state says a managed file
    exists but records no digest for it — the state cannot be trusted to decide
    whether removing the file is safe, so no operation may remove it silently.
    """

    current = digest_file(path)
    if current is None:
        return MISSING if not path.exists() else CONFLICT
    if digest_at_install is None:
        return CONFLICT
    return UNCHANGED if current == digest_at_install else USER_MODIFIED


def is_safe_to_replace(status: str) -> bool:
    """Only a file still holding the bytes the stack wrote may be replaced."""

    return status in (UNCHANGED, MISSING)


def is_safe_to_remove(status: str) -> bool:
    """Only a file still holding the bytes the stack wrote may be removed."""

    return status == UNCHANGED


__all__ = [
    "UNCHANGED",
    "USER_MODIFIED",
    "MISSING",
    "CONFLICT",
    "digest_bytes",
    "digest_file",
    "classify",
    "is_safe_to_replace",
    "is_safe_to_remove",
]
