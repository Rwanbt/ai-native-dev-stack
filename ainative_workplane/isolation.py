"""Start a verification command so that nothing it spawns can outlive it.

Killing a process tree by walking parent/child links only works while the
parent is still alive. A command that spawns a background child and then exits
leaves that child orphaned and unreachable by PID-tree termination, so it goes
on writing to the repository after the run that produced it was abandoned.
This module attaches the command to an OS-level container instead — a job
object on Windows, a session on POSIX — and terminates the container.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
from pathlib import Path
from typing import Any, Sequence


_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32() -> Any:
    """Return kernel32 with the job-object signatures declared.

    WHY: without argtypes/restype ctypes marshals handles as 32-bit ints, so a
    64-bit job handle is silently truncated and every later call fails.
    """

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _create_job() -> Any:
    """Create a job that kills every process still inside it when it closes."""

    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    information = _ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(information), ctypes.sizeof(information)):
        kernel32.CloseHandle(job)
        return None
    return job


class IsolatedProcess:
    """A running command plus the container that guarantees its cleanup."""

    def __init__(self, process: subprocess.Popen[bytes], job: Any = None):
        self.process = process
        self._job = job

    def terminate_tree(self) -> None:
        """Kill the command and every descendant, alive parent or not."""

        if os.name == "nt":
            self._terminate_windows()
        else:
            self._terminate_posix()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def _terminate_windows(self) -> None:
        """Kill the tree, then the job.

        WHY both: the job object is what reaches an orphan whose parent has
        already exited, which a PID walk cannot do; the PID walk is what still
        works when the job could not be created or the process could not be
        assigned to it. The adversarial suite asserts the outcome — no
        descendant survives — rather than which mechanism achieved it.
        """

        if self.process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=5)
        if self._job is not None:
            _kernel32().TerminateJobObject(self._job, 1)

    def _terminate_posix(self) -> None:
        try:
            os.killpg(self.process.pid, 9)
        except (ProcessLookupError, PermissionError):
            if self.process.poll() is None:
                self.process.kill()

    def close(self) -> None:
        if self._job is not None:
            _kernel32().CloseHandle(self._job)
            self._job = None


def spawn(argv: Sequence[str], cwd: str | Path) -> IsolatedProcess:
    """Start argv with its own OS container, pipes attached."""

    job = _create_job() if os.name == "nt" else None
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    if job is not None:
        # The window between start and assignment is small but real; a child
        # created inside it is caught by the PID-tree fallback above.
        kernel32 = _kernel32()
        if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
            kernel32.CloseHandle(job)
            job = None
    return IsolatedProcess(process, job)
