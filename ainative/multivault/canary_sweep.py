"""Cross-domain canary sweep: real plant, scan and cleanup over local surfaces.

GUARDED honesty: the sweep detects leaks and operational errors. It does not
and cannot prevent a hostile same-OS-user from reading files directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time

INFRASTRUCTURE_UNAVAILABLE = "INFRASTRUCTURE_UNAVAILABLE"
PERMISSION_DENIED = "PERMISSION_DENIED"
STORE_LOCATION_UNKNOWN = "STORE_LOCATION_UNKNOWN"
ADAPTER_SURFACE_UNKNOWN = "ADAPTER_SURFACE_UNKNOWN"
TIMEOUT = "TIMEOUT"
READ_ERROR = "READ_ERROR"
ENUMERATION_FAILURE = "ENUMERATION_FAILURE"
POSSIBLE_TAMPERING = "POSSIBLE_TAMPERING"
LEAK_CODE = "LEAK"

EXIT_COMPLETE_CLEAN = 0
EXIT_LEAK = 1
EXIT_INCOMPLETE = 2


@dataclass(frozen=True)
class CanarySurface:
    domain: str
    name: str
    kind: str
    root: Path | None


@dataclass(frozen=True)
class CanaryFinding:
    surface: str
    code: str
    detail: str


@dataclass(frozen=True)
class CanaryReport:
    exit_code: int
    leaks: tuple[CanaryFinding, ...]
    incomplete: tuple[CanaryFinding, ...]
    scanned: tuple[str, ...]
    assurance: str = field(default="GUARDED: detects leaks and operational errors; does not resist a hostile same-OS-user")


def marker_for(nonce: str, domain: str) -> bytes:
    return f"AINATIVE-CANARY nonce={nonce} domain={domain}\n".encode("utf-8")


def _scan_surface(surface: CanarySurface, marker: bytes, deadline: float) -> CanaryFinding | None:
    if surface.root is None:
        return CanaryFinding(surface.name, STORE_LOCATION_UNKNOWN, "no store location is known for this surface")
    if not surface.root.exists():
        return CanaryFinding(surface.name, INFRASTRUCTURE_UNAVAILABLE, "declared surface does not exist")
    if not surface.root.is_dir():
        return CanaryFinding(surface.name, ADAPTER_SURFACE_UNKNOWN, "declared surface is not a directory")
    try:
        paths = sorted(path for path in surface.root.rglob("*") if path.is_file())
    except PermissionError:
        return CanaryFinding(surface.name, PERMISSION_DENIED, "surface enumeration was denied")
    except OSError:
        return CanaryFinding(surface.name, ENUMERATION_FAILURE, "surface enumeration failed")
    for path in paths:
        if time.monotonic() > deadline:
            return CanaryFinding(surface.name, TIMEOUT, "scan exceeded its deadline")
        try:
            content = path.read_bytes()
        except PermissionError:
            return CanaryFinding(surface.name, PERMISSION_DENIED, "surface read was denied")
        except OSError:
            return CanaryFinding(surface.name, READ_ERROR, "surface read failed")
        if marker in content:
            return CanaryFinding(surface.name, LEAK_CODE, f"foreign marker found under {surface.domain}")
    return None


def run_canary_sweep(
    surfaces: tuple[CanarySurface, ...],
    *,
    nonce: str,
    timeout_seconds: float = 30.0,
) -> CanaryReport:
    """Plant in each domain, scan every surface, then clean up planted markers."""
    deadline = time.monotonic() + timeout_seconds
    leaks: list[CanaryFinding] = []
    incomplete: list[CanaryFinding] = []
    scanned: list[str] = []
    planted: list[Path] = []
    for surface in surfaces:
        if surface.root is None or not surface.root.is_dir():
            continue
        marker_file = surface.root / f".ainative-canary-{nonce}-{surface.domain}"
        try:
            marker_file.write_bytes(marker_for(nonce, surface.domain))
            planted.append(marker_file)
        except OSError:
            possible = CanaryFinding(surface.name, POSSIBLE_TAMPERING, "marker could not be planted")
            leaked = _scan_surface(surface, marker_for(nonce, surface.domain), deadline)
            if leaked is not None and leaked.code == LEAK_CODE:
                leaks.append(leaked)
            else:
                incomplete.append(possible)
            continue
        scanned.append(surface.name)
        for other in surfaces:
            if other.domain == surface.domain:
                continue
            finding = _scan_surface(other, marker_for(nonce, surface.domain), deadline)
            if finding is None:
                continue
            if finding.code == LEAK_CODE:
                leaks.append(CanaryFinding(finding.surface, LEAK_CODE, f"{surface.domain} marker reached {other.domain}"))
            else:
                incomplete.append(finding)
    cleanup_failed = False
    for path in planted:
        try:
            path.unlink()
        except OSError:
            cleanup_failed = True
    if cleanup_failed:
        incomplete.append(CanaryFinding("cleanup", POSSIBLE_TAMPERING, "a planted marker could not be removed"))
    all_incomplete = tuple(dict.fromkeys(incomplete))
    if leaks:
        return CanaryReport(EXIT_LEAK, tuple(leaks), all_incomplete, tuple(scanned))
    if all_incomplete:
        return CanaryReport(EXIT_INCOMPLETE, (), all_incomplete, tuple(scanned))
    return CanaryReport(EXIT_COMPLETE_CLEAN, (), (), tuple(scanned))


LEAK_CODE = "LEAK"