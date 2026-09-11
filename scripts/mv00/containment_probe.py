"""MV-00.6 — Windows Job Object containment spike (ADR-0014 section 13).

Proves or refutes, on the executing machine, that a Job Object with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and breakaway disabled:
  - kills the workload including detached descendants when every supervisor
    handle is closed (supervisor-loss fail-dead semantics);
  - denies CREATE_BREAKAWAY_FROM_JOB spawns (escape resistance).

Non-Windows platforms report UNKNOWN; no other platform is claimed.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
DETACHED_PROCESS = 0x00000008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000

CHILD_SOURCE = (
    "import os, subprocess, sys, time\n"
    "go = sys.argv[1]\n"
    "deadline = time.time() + 10\n"
    "while not os.path.exists(go):\n"
    "    if time.time() > deadline:\n"
    "        print('NO-GO', flush=True)\n"
    "        raise SystemExit(3)\n"
    "    time.sleep(0.05)\n"
    "detached = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], creationflags=8)\n"
    "print('GRANDCHILD', detached.pid, flush=True)\n"
    "try:\n"
    "    subprocess.Popen([sys.executable, '-c', 'pass'], creationflags=0x01000000)\n"
    "    print('BREAKAWAY_ALLOWED', flush=True)\n"
    "except OSError as error:\n"
    "    print('BREAKAWAY_DENIED', getattr(error, 'winerror', '?'), flush=True)\n"
    "print('CHILD_READY', flush=True)\n"
    "time.sleep(60)\n"
)


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class ContainmentReport:
    schema_version: int
    recorded_at: str
    platform: str
    result: str
    kill_on_close: bool
    detached_descendant_killed: bool
    breakaway_denied: bool
    evidence: tuple[str, ...]
    reason: str


def _kernel32():
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.CreateJobObjectW.restype = wintypes.HANDLE
    library.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    library.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    library.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    library.OpenProcess.restype = wintypes.HANDLE
    library.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    return library


def _process_alive(library, pid: int) -> bool:
    handle = library.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
    if not handle:
        return False
    library.CloseHandle(handle)
    return True


def _terminate(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)


def _report(**overrides) -> dict:
    base = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": sys.platform,
        "result": "NONE",
        "kill_on_close": False,
        "detached_descendant_killed": False,
        "breakaway_denied": False,
        "evidence": [],
        "reason": "",
    }
    base.update(overrides)
    return base


def run_probe(timeout: float = 20.0) -> dict:
    if os.name != "nt":
        return _report(result="UNKNOWN", reason="Windows Job Object semantics are unavailable on this platform")
    library = _kernel32()
    job = library.CreateJobObjectW(None, None)
    if not job:
        return _report(result="NONE", reason=f"CreateJobObjectW failed with error {ctypes.get_last_error()}")
    limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not library.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)):
        library.CloseHandle(job)
        return _report(result="NONE", reason=f"SetInformationJobObject failed with error {ctypes.get_last_error()}")

    grandchild_pid = None
    evidence: list[str] = []
    child = None
    try:
        with tempfile.TemporaryDirectory() as directory:
            go_file = Path(directory) / "go"
            child = subprocess.Popen(
                [sys.executable, "-c", CHILD_SOURCE, str(go_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if not library.AssignProcessToJobObject(job, wintypes.HANDLE(int(child._handle))):
                child.kill()
                child.wait(timeout=timeout)
                return _report(result="NONE", reason=f"AssignProcessToJobObject failed with error {ctypes.get_last_error()}")
            go_file.write_text("go", encoding="ascii")
            breakaway_denied = False
            child_ready = False
            deadline = time.time() + timeout
            while time.time() < deadline and not (grandchild_pid and breakaway_denied and child_ready):
                line = child.stdout.readline()
                if not line:
                    break
                text = line.strip()
                evidence.append(text)
                if text.startswith("GRANDCHILD"):
                    grandchild_pid = int(text.split()[1])
                elif text.startswith("BREAKAWAY_DENIED"):
                    breakaway_denied = True
                elif text.startswith("CHILD_READY"):
                    child_ready = True
            grandchild_alive_before = _process_alive(library, grandchild_pid) if grandchild_pid else False
            if not child_ready or not grandchild_alive_before:
                if grandchild_pid:
                    _terminate(grandchild_pid)
                child.kill()
                child.wait(timeout=timeout)
                return _report(
                    result="PARTIAL",
                    detached_descendant_killed=False,
                    breakaway_denied=breakaway_denied,
                    evidence=evidence,
                    reason="the workload did not reach a verifiable state before supervisor loss",
                )
            library.CloseHandle(job)
            job = None
            try:
                child.wait(timeout=timeout)
                child_killed = True
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=timeout)
                child_killed = False
            grandchild_killed = False
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not _process_alive(library, grandchild_pid):
                    grandchild_killed = True
                    break
                time.sleep(0.1)
            if not grandchild_killed:
                _terminate(grandchild_pid)
            kill_on_close = child_killed and grandchild_killed
            if kill_on_close and breakaway_denied:
                result = "VERIFIED"
                reason = "supervisor loss killed the workload including detached descendants and breakaway was denied"
            else:
                result = "PARTIAL"
                reason = "kill-on-close or breakaway semantics were not both proven"
            return _report(
                result=result,
                kill_on_close=kill_on_close,
                detached_descendant_killed=grandchild_killed,
                breakaway_denied=breakaway_denied,
                evidence=evidence,
                reason=reason,
            )
    finally:
        if job:
            library.CloseHandle(job)
        if child and child.poll() is None:
            child.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_probe()
    encoded = json.dumps(report, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())