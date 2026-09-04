"""One lifecycle mutation at a time, per project.

Two concurrent mutations would interleave a plan built against one state with
writes made against another. The lock is created complete — payload and all —
in one atomic step, and it records the owning process so a lock left by a crash
can be distinguished from a lock held by a live run.

`acquired_at` says when a claim was made. `claim_id` says which acquisition
owns it, so an old owner can never release a replacement that shares its
process metadata and timestamp.

A stale lock is reclaimed only when its recorded process is provably gone. A
lock whose owner cannot be judged is left alone and reported: deleting a live
owner's lock is exactly the failure the lock exists to prevent.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .errors import LifecycleError
from .state import LIFECYCLE_DIRNAME

LOCK_RELATIVE = LIFECYCLE_DIRNAME / "lifecycle.lock"

# A lock older than this whose owner is unknown is reported as stale-suspect but
# still not removed automatically; `--force-unlock` is the human decision.
STALE_AFTER_SECONDS = 3600


@dataclass(frozen=True)
class LockInfo:
    pid: int
    operation: str
    acquired_at: str
    host: str
    claim_id: str | None = None

    def to_record(self) -> dict:
        record = {"pid": self.pid, "operation": self.operation,
                  "acquired_at": self.acquired_at, "host": self.host}
        if self.claim_id:
            record["claim_id"] = self.claim_id
        return record


def lock_path(project: Path) -> Path:
    return project / LOCK_RELATIVE


def _mutation_guard_path(project: Path) -> Path:
    """A per-project OS-lock file that is not lifecycle data.

    Keeping this coordination primitive below `.ai-native/lifecycle` made a
    completed purge retain the lifecycle directory.  The lock belongs to the
    running processes, not to the installed project, so it lives in the system
    temporary directory and has a stable opaque name derived from the resolved
    project path.
    """

    identity = str(project.resolve(strict=False)).encode("utf-8")
    name = hashlib.sha256(identity).hexdigest() + ".lock"
    return Path(tempfile.gettempdir()) / "ainative-lock-guards" / name


@contextmanager
def _mutation_guard(project: Path) -> Iterator[None]:
    """Serialize ownership-file mutations without extending the lifecycle lock.

    A claim comparison and an unlink are separate filesystem operations.  A
    second lifecycle process could force-replace a claim in that interval, so
    the old owner would still unlink the replacement despite distinct claim
    IDs.  This short-lived OS lock covers every create, reclaim, force-remove,
    and release decision; it is never held while an operation mutates project
    files.  The operating system releases it if a process crashes.
    """

    path = _mutation_guard_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    locked = False
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


ERROR_INVALID_PARAMETER = 87
ERROR_ACCESS_DENIED = 5
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def _hostname() -> str:
    return (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME")
            or getattr(os, "uname", lambda: None)() and os.uname().nodename or "")


def _windows_process_alive(pid: int) -> bool | None:
    import ctypes  # local: only Windows needs it

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        code = ctypes.get_last_error() or kernel32.GetLastError()
        if code == ERROR_INVALID_PARAMETER:
            return False           # no such process
        if code == ERROR_ACCESS_DENIED:
            return True            # exists, another user owns it
        return None
    exit_code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    if not ok:
        return None
    return exit_code.value == STILL_ACTIVE


def _process_alive(pid: int) -> bool | None:
    """True/False when we can tell, None when the platform will not say.

    None is the important answer: an unknown owner must never have its lock
    reclaimed automatically.
    """

    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            return _windows_process_alive(pid)
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True   # exists, owned by someone else
    except ProcessLookupError:
        return False
    except OSError:
        return None


def _owner_alive(info: "LockInfo") -> bool | None:
    """A pid is only meaningful on the machine that recorded it."""

    here = _hostname()
    if info.host and here and info.host != here:
        return None
    return _process_alive(info.pid)


def read(project: Path) -> LockInfo | None:
    path = lock_path(project)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        claim_id = payload.get("claim_id")
        return LockInfo(pid=int(payload["pid"]), operation=str(payload.get("operation", "")),
                        acquired_at=str(payload.get("acquired_at", "")),
                        host=str(payload.get("host", "")),
                        claim_id=claim_id if isinstance(claim_id, str) and claim_id else None)
    except (KeyError, TypeError, ValueError):
        return None


def _age_seconds(info: LockInfo) -> float:
    try:
        acquired = datetime.fromisoformat(info.acquired_at)
    except ValueError:
        return 0.0
    if acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - acquired).total_seconds()


def describe(project: Path) -> dict | None:
    """What `doctor` reports about the lock, without touching it."""

    info = read(project)
    if info is None:
        return None
    alive = _owner_alive(info)
    age = _age_seconds(info)
    return {**info.to_record(), "owner_alive": alive, "age_seconds": int(age),
            "stale_suspect": alive is False or (alive is None and age > STALE_AFTER_SECONDS)}


def _reclaim_if_dead(project: Path, info: LockInfo) -> bool:
    """Remove a lock only when its owner is provably gone."""

    if _owner_alive(info) is False:
        lock_path(project).unlink(missing_ok=True)
        return True
    return False


def _release(project: Path, info: LockInfo) -> None:
    """Remove the lock only while it is still this operation's own.

    After a `--force-unlock` took the lock away and handed it to someone else,
    the original owner's `finally` deleted the *new* owner's lock and left two
    operations believing they held it (EMP-LC-036). The claim token, rather
    than timestamp metadata, is the ownership proof (EMP-LC-041).
    """

    current = read(project)
    if (info.claim_id is not None and current is not None
            and current.claim_id == info.claim_id):
        lock_path(project).unlink(missing_ok=True)


def _claim(path: Path, payload: str) -> bool:
    """Create the lock complete, or not at all. True when this process won it.

    `O_EXCL` makes the *existence* atomic, but the payload was written after,
    leaving a window in which the file existed and was empty. A second process
    that looked in that window read nothing, concluded the lock was invalid, and
    deleted a live owner's claim (EMP-LC-030).

    Writing the payload to a temporary file and hard-linking it into place makes
    creation and content one step: another process either sees no file, or sees
    a complete one. Where `os.link` is unavailable the O_EXCL path is used and
    an unreadable lock is retained rather than removed, which is slower to
    recover but never wrong.
    """

    # Unique per attempt, not per process: two threads share a pid, and a
    # shared staging name let one truncate the file the other was about to
    # link into place.
    descriptor, name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    staging = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        try:
            os.link(staging, path)
            return True
        except FileExistsError:
            return False
        except (OSError, NotImplementedError, AttributeError):
            handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(payload)
            return True
    finally:
        staging.unlink(missing_ok=True)


@contextmanager
def acquire(project: Path, operation: str, *, force: bool = False) -> Iterator[LockInfo]:
    path = lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = LockInfo(pid=os.getpid(), operation=operation,
                    acquired_at=datetime.now(timezone.utc).isoformat(),
                    host=_hostname(), claim_id=str(uuid.uuid4()))
    payload = json.dumps(info.to_record(), sort_keys=True) + "\n"

    with _mutation_guard(project):
        for attempt in range(2):
            try:
                won = _claim(path, payload)
            except FileExistsError:
                won = False
            except OSError as error:
                if error.errno == errno.EACCES:
                    raise LifecycleError("LOCK_HELD", f"cannot create {path}: {error}") from error
                raise

            if won:
                break

            existing = read(project)
            if attempt == 0 and force:
                # A human said this lock is stale. Retrying without removing it
                # just failed again on the next attempt (EMP-LC-008).
                try:
                    path.unlink(missing_ok=True)
                except OSError as error:
                    # A refused unlink is a refusal to report, not a traceback
                    # to print at the user (EMP-LC-039).
                    raise LifecycleError(
                        "LOCK_HELD",
                        f"cannot remove {path}: {error}") from error
                continue
            if existing is None:
                # Unreadable. That is either corruption or a claim being made right
                # now, and this code cannot tell them apart — so it refuses rather
                # than deleting what may be a live owner's lock.
                raise LifecycleError(
                    "LOCK_HELD",
                    f"{path} exists but cannot be read as a lock. If no lifecycle "
                    "operation is running, re-run with --force-unlock.")
            if attempt == 0 and _reclaim_if_dead(project, existing):
                continue
            raise LifecycleError(
                "LOCK_HELD",
                f"another lifecycle operation holds the lock (pid {existing.pid}, "
                f"{existing.operation or 'unknown'}). If that process is gone, "
                f"re-run with --force-unlock.",
                holder=existing.to_record()) from None
        else:
            raise LifecycleError("LOCK_HELD", f"could not acquire {path} after reclaiming a stale lock")

    try:
        yield info
    finally:
        with _mutation_guard(project):
            _release(project, info)


__all__ = ["LockInfo", "lock_path", "read", "describe", "acquire", "LOCK_RELATIVE",
           "STALE_AFTER_SECONDS"]
