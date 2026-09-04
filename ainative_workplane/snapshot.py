"""PR-04 scoped repository snapshot primitives."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .contracts import canonical_digest, canonical_path, generate_uid, validate_case_collisions, validate_artifact


class SnapshotError(RuntimeError):
    pass


def _identity(status: os.stat_result) -> tuple[int, int, int, int]:
    return (status.st_size, status.st_mtime_ns, status.st_ino, status.st_dev)


def _digest_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file and refuse the result if it changed while being read.

    WHY: a snapshot that hashes a file being rewritten records a digest of a
    state that never existed, and every later freshness comparison is then
    against fiction. Size, mtime and inode are cheap and portable enough to
    catch that; they cannot catch a rewrite that preserves all three, which is
    stated as residual risk rather than implied away.
    """

    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    if _identity(path.stat()) != _identity(before):
        raise SnapshotError("SNAPSHOT_RACE")
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


def _git_state(root: Path) -> tuple[str, bool]:
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], check=True, capture_output=True, text=True, timeout=5).stdout != ""
    except (OSError, subprocess.SubprocessError) as exc:
        raise SnapshotError("REPOSITORY_STATE_UNAVAILABLE") from exc
    if not head:
        raise SnapshotError("REPOSITORY_STATE_UNAVAILABLE")
    return head, dirty


def build_repository_snapshot(
    root: str | os.PathLike[str],
    *,
    scope: Iterable[str],
    dependency_paths: Iterable[str],
    command_registry_digest: str,
    policy_digest: str,
    uid: str | None = None,
) -> dict[str, Any]:
    """Collect a validated, content-bound repository snapshot from one checkout."""

    base = Path(root).resolve()
    scope_paths = validate_case_collisions([canonical_path(path) for path in scope])
    dependency_list = validate_case_collisions([canonical_path(path) for path in dependency_paths])
    head, dirty = _git_state(base)
    snapshot = {
        "schema_name": "repository_snapshot",
        "schema_version": 1,
        "uid": uid or generate_uid("snapshot"),
        "head": head,
        "dirty": dirty,
        "scope": list(scope_paths),
        "dependency_paths": list(dependency_list),
        "dependencies": [],
        "content_digest": canonical_digest(snapshot_files(base, scope_paths)),
        "dependency_digest": canonical_digest(snapshot_files(base, dependency_list)),
        "command_registry_digest": command_registry_digest,
        "policy_digest": policy_digest,
    }
    validate_artifact(snapshot)
    return snapshot


def snapshot_reference(snapshot: dict[str, Any]) -> dict[str, str]:
    """Return the immutable reference used to bind a verification run."""

    validate_artifact(snapshot)
    return {"uid": snapshot["uid"], "digest": canonical_digest(snapshot)}
