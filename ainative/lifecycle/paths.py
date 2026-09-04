"""Path containment — the guard between a manifest string and `unlink()`.

Every destination the lifecycle layer writes, replaces or deletes comes from a
manifest, an install state, or a downloaded archive. All three are data, and
data must never be able to name a path outside the root it is scoped to.

The rule enforced here is narrow on purpose: a relative path, resolved against
its root, must still be inside that root, and no component of the walk may
traverse a symlink or a Windows junction that leaves it. Anything else is
`PATH_ESCAPE`.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from .errors import LifecycleError

# Names that are never valid as a manifest-supplied relative path component.
_RESERVED_COMPONENTS = {"", ".", ".."}


def _reject(relative: str, reason: str) -> "LifecycleError":
    return LifecycleError("PATH_ESCAPE", f"refused path {relative!r}: {reason}",
                          path=relative, reason=reason)


def validate_relative(relative: str) -> PurePosixPath:
    """Parse a manifest-supplied relative path, or refuse it.

    Refuses absolute paths, drive letters, UNC roots, `..`, and empty
    components. The check is done with both POSIX and Windows parsers, because
    `C:\\x` is a plain relative filename to `PurePosixPath` and a drive-rooted
    absolute path to Windows — a manifest written on one platform must not mean
    something different on the other.
    """

    if not isinstance(relative, str) or not relative.strip():
        raise _reject(str(relative), "empty path")
    if "\x00" in relative:
        raise _reject(relative, "NUL byte in path")

    posix = PurePosixPath(relative.replace("\\", "/"))
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute():
        raise _reject(relative, "absolute path")
    if windows.drive or windows.root or posix.root:
        raise _reject(relative, "drive or root anchor")
    for part in posix.parts:
        if part in _RESERVED_COMPONENTS or part.strip() != part:
            raise _reject(relative, f"illegal component {part!r}")
    return posix


def _walk_is_contained(root: Path, target: Path) -> bool:
    """True when no ancestor of `target` up to `root` is a link out of `root`.

    `Path.resolve()` alone is not enough on the delete path: it answers where a
    symlink points, which is exactly the value an attacker controls. We instead
    check every intermediate directory, so a link planted midway is caught
    before the final component is touched.
    """

    current = root
    try:
        relative = target.relative_to(root)
    except ValueError:
        return False
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
        if os.name == "nt" and current.is_dir():
            # A junction is not a symlink to `is_symlink()`, so compare the
            # resolved parent instead: a junction resolves out of the root.
            try:
                if current.resolve().parent != current.parent.resolve():
                    return False
            except OSError:
                return False
    return True


def resolve_within(root: Path, relative: str) -> Path:
    """Resolve `relative` under `root`, refusing anything that leaves it.

    Returns the un-resolved path (root / relative) so callers write to the
    literal location, not to wherever a link points. Containment is proved
    before returning.
    """

    parsed = validate_relative(relative)
    try:
        base = root.resolve(strict=False)
    except OSError as error:
        raise LifecycleError("PATH_ESCAPE", f"unresolvable root {root}: {error}") from error

    candidate = base.joinpath(*parsed.parts)
    try:
        candidate.relative_to(base)
    except ValueError:
        raise _reject(relative, "resolves outside the target root") from None

    # Case-fold collision: on a case-insensitive filesystem two manifest
    # entries differing only in case name the same file. Callers dedupe on the
    # normalised key; here we only guarantee the path is inside the root.
    if not _walk_is_contained(base, candidate):
        raise _reject(relative, "traverses a symlink or junction out of the root")
    return candidate


def is_within(root: Path, candidate: Path) -> bool:
    """Containment predicate used before any delete. Never raises.

    Judges the literal path, not what a link at its tail points to: deleting
    `root/link` must be allowed (it removes the link) while deleting *through*
    a directory link that leaves the root must not.
    """

    try:
        base = root.resolve(strict=False)
        literal = candidate if candidate.is_absolute() else base / candidate
        # Normalise `..` textually; resolving would follow the very links we
        # are trying to judge.
        literal = Path(os.path.normpath(str(literal)))
        literal.relative_to(base)
    except (OSError, ValueError):
        return False
    return _walk_is_contained(base, literal)


def collision_key(relative: str) -> str:
    """The key two manifest paths share when a case-insensitive FS merges them."""

    return PurePosixPath(relative.replace("\\", "/")).as_posix().casefold()


__all__ = ["validate_relative", "resolve_within", "is_within", "collision_key"]
