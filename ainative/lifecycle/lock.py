"""One lifecycle mutation at a time, per project.

Two concurrent mutations would interleave a plan built against one state with
writes made against another. The lock is a file created with `O_EXCL`, which is
atomic on every platform we support, and it records the owning process so a
lock left by a crash can be distinguished from a lock held by a live run.

A stale lock is reclaimed only when its recorded process is provably gone. A
lock whose owner cannot be judged is left alone and reported: deleting a live
owner's lock is exactly the failure the lock exists to prevent.
"""

from __future__ import annotations

import errno
import json
import os
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

    def to_record(self) -> dict:
        return {"pid": self.pid, "operation": self.operation,
                "acquired_at": self.acquired_at, "host": self.host}


def lock_path(project: Path) -> Path:
    return project / LOCK_RELATIVE


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
        return LockInfo(pid=int(payload["pid"]), operation=str(payload.get("operation", "")),
                        acquired_at=str(payload.get("acquired_at", "")),
                        host=str(payload.get("host", "")))
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


@contextmanager
def acquire(project: Path, operation: str, *, force: bool = False) -> Iterator[LockInfo]:
    path = lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = LockInfo(pid=os.getpid(), operation=operation,
                    acquired_at=datetime.now(timezone.utc).isoformat(),
                    host=_hostname())
    payload = json.dumps(info.to_record(), sort_keys=True) + "\n"

    for attempt in range(2):
        try:
            handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = read(project)
            if existing is None:
                # Unreadable lock file: it is not a valid claim, so replace it.
                path.unlink(missing_ok=True)
                continue
            if attempt == 0 and force:
                # A human said this lock is stale. Retrying without removing it
                # just failed again on the next O_EXCL (EMP-LC-008).
                path.unlink(missing_ok=True)
                continue
            if attempt == 0 and _reclaim_if_dead(project, existing):
                continue
            raise LifecycleError(
                "LOCK_HELD",
                f"another lifecycle operation holds the lock (pid {existing.pid}, "
                f"{existing.operation or 'unknown'}). If that process is gone, "
                f"re-run with --force-unlock.",
                holder=existing.to_record()) from None
        except OSError as error:
            if error.errno == errno.EACCES:
                raise LifecycleError("LOCK_HELD", f"cannot create {path}: {error}") from error
            raise
        else:
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                yield info
            finally:
                path.unlink(missing_ok=True)
            return

    raise LifecycleError("LOCK_HELD", f"could not acquire {path} after reclaiming a stale lock")


__all__ = ["LockInfo", "lock_path", "read", "describe", "acquire", "LOCK_RELATIVE",
           "STALE_AFTER_SECONDS"]
