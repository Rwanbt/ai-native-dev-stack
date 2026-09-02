"""PR-04 scoped repository snapshot primitives."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

from .contracts import canonical_path, validate_case_collisions


class SnapshotError(RuntimeError):
    pass


def _digest_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_files(root: str | os.PathLike[str], paths: Iterable[str]) -> dict[str, str]:
    """Return deterministic content digests for a safe, repository-relative scope."""

    base = Path(root).resolve()
    canonical = validate_case_collisions([canonical_path(path) for path in paths])
    result: dict[str, str] = {}
    for relative in canonical:
        path = base / relative
        resolved = path.resolve()
        if base not in resolved.parents and resolved != base:
            raise SnapshotError("SECURITY_REJECTED")
        if path.is_symlink():
            raise SnapshotError("SECURITY_REJECTED")
        if not path.is_file() or not path.stat().st_mode:
            raise SnapshotError("SECURITY_REJECTED")
        mode = path.stat().st_mode
        if not os.path.isfile(path) or (mode & 0o170000) != 0o100000:
            raise SnapshotError("SECURITY_REJECTED")
        result[relative] = _digest_file(path)
    return dict(sorted(result.items()))
