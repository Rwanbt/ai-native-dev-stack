"""Deterministic candidate-object scanner for governed Git pushes (ADR-0016 section 15).

Computes the objects a proposed transfer would make newly reachable and scans
them for secrets, policy-forbidden paths, oversized binaries and Git LFS
pointers. The scanner never touches the network: a missing object, a shallow
repository or a partial/promisor repository is INCOMPLETE, which callers must
treat as fail-closed for sensitive classifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import fnmatch
import os
from pathlib import Path
import shutil
import subprocess
from typing import Mapping


DEFAULT_SECRET_PATTERNS: tuple[bytes, ...] = (
    b"-----BEGIN RSA PRIVATE KEY",
    b"-----BEGIN OPENSSH PRIVATE KEY",
    b"-----BEGIN EC PRIVATE KEY",
    b"-----BEGIN PRIVATE KEY",
    b"AKIA",
    b"github_pat_",
    b"ghp_",
    b"xoxb-",
)

LARGE_BINARY_THRESHOLD_BYTES = 10 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192
DEFAULT_GIT_TIMEOUT_SECONDS = 60
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


class ScanVerdict(str, Enum):
    PASS = "PASS"
    LEAK = "LEAK"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class ScanFinding:
    category: str
    object_id: str
    path: str
    detail: str


@dataclass(frozen=True)
class CandidateScanResult:
    verdict: ScanVerdict
    findings: tuple[ScanFinding, ...]
    objects_examined: int
    blobs_scanned: int
    reason: str


def default_git_environment(git_executable: str) -> dict[str, str]:
    """Positive environment: empty base plus explicit values only (ADR-0016 section 4)."""
    environment = {
        "PATH": str(Path(git_executable).parent),
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    system_root = os.environ.get("SYSTEMROOT")
    if system_root and Path(system_root).is_absolute():
        environment["SYSTEMROOT"] = system_root
    return environment


def _is_zero_oid(value: str) -> bool:
    return len(value) in (40, 64) and value.strip("0") == ""


class CandidateObjectScanner:
    """Read-only, network-free scan of the objects a push would newly expose."""

    def __init__(
        self,
        repository: Path,
        *,
        forbidden_paths: tuple[str, ...] = (),
        secret_patterns: tuple[bytes, ...] = DEFAULT_SECRET_PATTERNS,
        max_binary_bytes: int = LARGE_BINARY_THRESHOLD_BYTES,
        git_executable: str | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS,
    ):
        executable = git_executable or shutil.which("git")
        if not executable:
            raise ValueError("a Git executable is required for candidate scanning")
        if timeout_seconds <= 0:
            raise ValueError("candidate scanning requires a positive timeout")
        self._git = executable
        self._repository = Path(repository)
        self._forbidden_paths = tuple(forbidden_paths)
        self._secret_patterns = tuple(secret_patterns)
        self._max_binary_bytes = max_binary_bytes
        self._environment = dict(environment) if environment is not None else default_git_environment(executable)
        self._timeout_seconds = timeout_seconds

    def scan(self, source_oid: str, remote_base_oid: str | None, refspec: str) -> CandidateScanResult:
        reason = self._preflight(source_oid, refspec)
        if reason:
            return CandidateScanResult(ScanVerdict.INCOMPLETE, (), 0, 0, reason)
        entries = self._candidate_objects(source_oid, remote_base_oid)
        if entries is None:
            return CandidateScanResult(ScanVerdict.INCOMPLETE, (), 0, 0, "candidate object enumeration failed")
        metadata = self._object_metadata([oid for oid, _path in entries])
        if metadata is None:
            return CandidateScanResult(ScanVerdict.INCOMPLETE, (), len(entries), 0, "missing or unreadable objects in the candidate set")
        blobs = [(oid, path) for oid, path in entries if metadata[oid][0] == "blob"]
        contents = self._blob_contents([oid for oid, _path in blobs])
        if contents is None:
            return CandidateScanResult(ScanVerdict.INCOMPLETE, (), len(entries), len(blobs), "blob content is unreadable")
        findings = self._scan_blobs(blobs, contents)
        if findings:
            return CandidateScanResult(ScanVerdict.LEAK, tuple(findings), len(entries), len(blobs), f"{len(findings)} policy finding(s) in the candidate object set")
        return CandidateScanResult(ScanVerdict.PASS, (), len(entries), len(blobs), "candidate object set is clean")

    def _preflight(self, source_oid: str, refspec: str) -> str | None:
        if not source_oid or not refspec:
            return "a source object id and an exact refspec are required"
        source = refspec.split(":", 1)[0].lstrip("+")
        if not source:
            return "refspec has no source"
        resolved = self._run(["rev-parse", "--verify", "--quiet", source])
        if resolved is None or resolved.returncode != 0:
            return "refspec source does not resolve in the repository"
        if resolved.stdout.strip().decode("ascii", "replace") != source_oid:
            return "refspec source does not match the push intent source object"
        shallow = self._run(["rev-parse", "--is-shallow-repository"])
        if shallow is None or shallow.returncode != 0:
            return "repository state is unreadable"
        if shallow.stdout.strip() == b"true":
            return "shallow repository; the candidate set would be incomplete"
        config = self._run(["config", "--local", "--null", "--list"])
        if config is None or config.returncode != 0:
            return "repository configuration is unreadable"
        for entry in config.stdout.split(b"\x00"):
            if not entry:
                continue
            key = entry.split(b"\n", 1)[0].decode("utf-8", "replace").lower()
            if key == "extensions.partialclone" or key.endswith(".promisor") or key.endswith(".partialclonefilter"):
                return "partial/promisor repository configuration; lazy fetch is denied"
        return None

    def _candidate_objects(self, source_oid: str, remote_base_oid: str | None) -> list[tuple[str, str | None]] | None:
        arguments = ["rev-list", "--objects", source_oid]
        if remote_base_oid and not _is_zero_oid(remote_base_oid):
            arguments += ["--not", remote_base_oid]
        result = self._run(arguments)
        if result is None or result.returncode != 0:
            return None
        entries: list[tuple[str, str | None]] = []
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            oid, _separator, path = line.partition(" ")
            entries.append((oid, path or None))
        return entries

    def _object_metadata(self, oids: list[str]) -> dict[str, tuple[str, int]] | None:
        if not oids:
            return {}
        result = self._run(["cat-file", "--batch-check"], input_bytes="\n".join(oids).encode("ascii") + b"\n")
        if result is None or result.returncode != 0:
            return None
        metadata: dict[str, tuple[str, int]] = {}
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split(" ")
            if len(parts) != 3:
                return None
            try:
                metadata[parts[0]] = (parts[1], int(parts[2]))
            except ValueError:
                return None
        if len(metadata) != len(set(oids)):
            return None
        return metadata

    def _blob_contents(self, oids: list[str]) -> dict[str, bytes] | None:
        if not oids:
            return {}
        result = self._run(["cat-file", "--batch"], input_bytes="\n".join(oids).encode("ascii") + b"\n")
        if result is None or result.returncode != 0:
            return None
        stream = result.stdout
        position = 0
        contents: dict[str, bytes] = {}
        for oid in oids:
            newline = stream.find(b"\n", position)
            if newline < 0:
                return None
            header = stream[position:newline].split(b" ")
            if len(header) != 3 or header[0].decode("ascii", "replace") != oid or header[1] != b"blob":
                return None
            try:
                size = int(header[2])
            except ValueError:
                return None
            start = newline + 1
            end = start + size
            if stream[end:end + 1] != b"\n":
                return None
            contents[oid] = stream[start:end]
            position = end + 1
        return contents

    def _scan_blobs(self, blobs: list[tuple[str, str | None]], contents: dict[str, bytes]) -> list[ScanFinding]:
        findings: list[ScanFinding] = []
        for oid, path in blobs:
            content = contents[oid]
            decorated_path = path or ""
            if content.startswith(LFS_POINTER_PREFIX):
                findings.append(ScanFinding("lfs_pointer", oid, decorated_path, "Git LFS pointer requires an LFS network transfer"))
            for pattern in self._secret_patterns:
                if pattern in content:
                    findings.append(ScanFinding("secret", oid, decorated_path, f"content matches secret pattern {pattern!r}"))
            if path:
                for pattern in self._forbidden_paths:
                    if fnmatch.fnmatchcase(path, pattern):
                        findings.append(ScanFinding("forbidden_path", oid, path, f"path matches forbidden pattern {pattern!r}"))
            if len(content) > self._max_binary_bytes and b"\x00" in content[:BINARY_SNIFF_BYTES]:
                findings.append(ScanFinding("large_binary", oid, decorated_path, f"binary blob of {len(content)} bytes exceeds {self._max_binary_bytes}"))
        return findings

    def _run(self, arguments: list[str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes] | None:
        try:
            return subprocess.run(
                [self._git, *arguments],
                cwd=str(self._repository),
                env=self._environment,
                input=input_bytes,
                capture_output=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None