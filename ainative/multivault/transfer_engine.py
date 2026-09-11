"""Governed fetch and push transfer engine (ADR-0016 sections 4-21).

The engine is the governed network writer: one positive Git environment used
for both validation and the actual transfer, destination/transport validation
before any network use, sensitive secondary-network refusal, a push lock held
through the transfer, candidate-object scanning, and single-use capability
authorization before the push executes.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Callable, Mapping

from .git_authority import (
    FetchTransferEvidence,
    GitTransportPolicy,
    LastVerifiedRepositoryState,
    build_fetch_evidence,
    compare_repository_state,
    normalize_remote_url,
    unapproved_remotes,
    validate_remote,
    validate_transport,
)
from .git_scanner import (
    CandidateObjectScanner,
    CandidateScanResult,
    ScanVerdict,
    default_git_environment,
)
from .push_guard import (
    GovernedPushAuthority,
    GovernedPushCapability,
    PushAuthorization,
    PushIntent,
)
from .schema import SecurityClassification, digest as canonical_digest


FETCH_DESTINATION_DENIED = "AINATIVE_FETCH_DESTINATION_DENIED"
PUSH_DESTINATION_DENIED = "AINATIVE_PUSH_DESTINATION_DENIED"
SECONDARY_NETWORK_DENIED = "AINATIVE_SECONDARY_GIT_NETWORK_DENIED"
LFS_NETWORK_DENIED = "AINATIVE_LFS_NETWORK_DENIED"
FORCE_PUSH_DENIED = "AINATIVE_FORCE_PUSH_DENIED"
REF_DELETION_DENIED = "AINATIVE_REF_DELETION_DENIED"
PUSH_LOCK_HELD = "AINATIVE_PUSH_LOCK_HELD"
PUSH_SCAN_LEAK = "AINATIVE_PUSH_SCAN_LEAK"
PUSH_SCAN_INCOMPLETE = "AINATIVE_PUSH_SCAN_INCOMPLETE"
PUSH_SOURCE_CHANGED = "AINATIVE_PUSH_SOURCE_CHANGED"
SUBMODULE_NETWORK_DENIED = "AINATIVE_SUBMODULE_GIT_NETWORK_DENIED"
UNAPPROVED_REMOTES_DENIED = "AINATIVE_UNAPPROVED_REMOTES_DENIED"
TRANSFER_ENVIRONMENT_DRIFT = "AINATIVE_TRANSFER_ENVIRONMENT_DRIFT"
FETCH_FAILED = "AINATIVE_FETCH_FAILED"
PUSH_FAILED = "AINATIVE_PUSH_FAILED"
DEFAULT_TRANSFER_TIMEOUT_SECONDS = 300

SENSITIVE_CLASSES = (SecurityClassification.CONFIDENTIAL, SecurityClassification.CRITICAL)


@dataclass(frozen=True)
class TransferOutcome:
    decision: str
    code: str
    reason: str
    evidence: FetchTransferEvidence | None = None
    repository_state: LastVerifiedRepositoryState | None = None


def _secondary_network_arguments(operation: str) -> list[str]:
    common = ["-c", "submodule.recurse=false", "-c", "core.hooksPath=" + os.devnull]
    if operation == "fetch":
        return ["-c", "fetch.recurseSubmodules=false", *common]
    return ["-c", "push.recurseSubmodules=no", *common]


class PushPreparation:
    """One prepared governed push; the lock stays held until complete or abort."""

    def __init__(
        self,
        engine: "GovernedTransferEngine",
        intent: PushIntent,
        scan: CandidateScanResult,
        capability: GovernedPushCapability,
        stdin_text: str,
        lock_path: Path,
        lock_fd: int,
        pre_state: LastVerifiedRepositoryState,
    ):
        self._engine = engine
        self.pre_state = pre_state
        self.intent = intent
        self.scan = scan
        self.capability = capability
        self.stdin_text = stdin_text
        self.lock_path = lock_path
        self._lock_fd = lock_fd
        self._finished = False

    def execute(self, authorize: Callable[[GovernedPushCapability, str], PushAuthorization] | None = None) -> TransferOutcome:
        return self._engine._complete_push(self, authorize)

    def abort(self) -> None:
        self._engine._abort_push(self)


class GovernedTransferEngine:
    """Governed fetch/push writer for one repository, remote and transport."""

    def __init__(
        self,
        repository: Path,
        *,
        approved_remote,
        transport_policy: GitTransportPolicy,
        push_authority: GovernedPushAuthority,
        classification: SecurityClassification,
        forbidden_paths: tuple[str, ...] = (),
        git_executable: str | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = DEFAULT_TRANSFER_TIMEOUT_SECONDS,
    ):
        executable = git_executable or shutil.which("git")
        if not executable:
            raise ValueError("a Git executable is required for governed transfers")
        if timeout_seconds <= 0:
            raise ValueError("governed transfers require a positive timeout")
        self._repository = Path(repository)
        self._approved_remote = approved_remote
        self._transport_policy = transport_policy
        self._push_authority = push_authority
        self._classification = classification
        self._git = executable
        self._environment = dict(environment) if environment is not None else default_git_environment(executable)
        self._timeout_seconds = timeout_seconds
        self._scanner = CandidateObjectScanner(
            repository,
            forbidden_paths=forbidden_paths,
            git_executable=executable,
            environment=self._environment,
            timeout_seconds=timeout_seconds,
        )

    def fetch(
        self,
        *,
        requested_refs: tuple[str, ...],
        observed_remote,
        observed_transport,
        verified_at: str,
    ) -> TransferOutcome:
        evidence_result = build_fetch_evidence(
            self._approved_remote,
            self._transport_policy,
            observed_remote,
            observed_transport,
            requested_refs,
            verified_at,
            self._classification,
        )
        if evidence_result.decision != "ALLOW" or evidence_result.evidence is None:
            return TransferOutcome("DENY", FETCH_DESTINATION_DENIED, evidence_result.reason)
        guard = self._sensitive_network_error()
        if guard is not None:
            return TransferOutcome("DENY", guard[0], guard[1])
        arguments = _secondary_network_arguments("fetch") + [
            "fetch",
            "--no-tags",
            self._approved_remote.canonical_fetch_url,
            *requested_refs,
        ]
        result = self._run(arguments)
        if result is None or result.returncode != 0:
            return TransferOutcome("DENY", FETCH_FAILED, self._failure_detail(result))
        evidence = evidence_result.evidence
        evidence_digest = canonical_digest({
            "remote": evidence.verified_remote_identity.stable_repository_id,
            "transport": evidence.effective_transport_config_digest,
            "refs": sorted(evidence.requested_refs),
            "verified_at": evidence.verified_at,
        })
        state = self._capture_repository_state(verified_at, evidence_digest)
        return TransferOutcome("ALLOW", "OK", "governed fetch completed", evidence, state)

    def begin_push(
        self,
        *,
        source_oid: str,
        expected_remote_base_oid: str,
        target_ref: str,
        exact_refspec: str,
        observed_remote,
        observed_transport,
        expected_git_identity: str,
    ) -> "PushPreparation | TransferOutcome":
        if exact_refspec.startswith("+"):
            return TransferOutcome("DENY", FORCE_PUSH_DENIED, "force push is denied by default")
        source_ref = exact_refspec.split(":", 1)[0].lstrip("+")
        if ":" not in exact_refspec or not source_ref:
            return TransferOutcome("DENY", REF_DELETION_DENIED, "remote ref deletion is denied by default")
        guard = self._sensitive_network_error()
        if guard is not None:
            return TransferOutcome("DENY", guard[0], guard[1])
        scan = self._scanner.scan(source_oid, expected_remote_base_oid, exact_refspec)
        if scan.verdict is ScanVerdict.LEAK:
            return TransferOutcome("DENY", PUSH_SCAN_LEAK, scan.reason)
        if scan.verdict is ScanVerdict.INCOMPLETE:
            return TransferOutcome("DENY", PUSH_SCAN_INCOMPLETE, scan.reason)
        remote_verdict = validate_remote(self._approved_remote, observed_remote, self._classification)
        if remote_verdict.decision != "ALLOW":
            return TransferOutcome("DENY", PUSH_DESTINATION_DENIED, remote_verdict.reason)
        transport_verdict = validate_transport(self._transport_policy, observed_transport)
        if transport_verdict.decision != "ALLOW":
            return TransferOutcome("DENY", PUSH_DESTINATION_DENIED, transport_verdict.reason)
        lock = self._acquire_push_lock()
        if lock is None:
            return TransferOutcome("DENY", PUSH_LOCK_HELD, "a governed push is already in progress")
        lock_path, lock_fd = lock
        resolved = self._run(["rev-parse", "--verify", "--quiet", source_ref])
        if resolved is None or resolved.returncode != 0 or resolved.stdout.strip().decode("ascii", "replace") != source_oid:
            self._release_push_lock(lock_path, lock_fd)
            return TransferOutcome("DENY", PUSH_SOURCE_CHANGED, "the source ref no longer matches the push intent")
        pre_state = self._capture_repository_state("pending", scan.scan_result_digest)
        if pre_state is None:
            self._release_push_lock(lock_path, lock_fd)
            return TransferOutcome("DENY", SECONDARY_NETWORK_DENIED, "repository state cannot be captured; the transfer environment is unverified")
        intent = PushIntent(
            source_oid=source_oid,
            expected_remote_base_oid=expected_remote_base_oid,
            target_ref=target_ref,
            exact_refspec=exact_refspec,
            approved_remote=self._approved_remote,
            transport_policy=self._transport_policy,
            candidate_object_set_digest=scan.candidate_set_digest,
            scan_result_digest=scan.scan_result_digest,
            expected_git_identity=expected_git_identity,
        )
        capability = self._push_authority.issue(intent)
        local_ref = source_ref if source_ref.startswith("refs/") else source_oid
        stdin_text = f"{local_ref} {source_oid} {target_ref} {expected_remote_base_oid}\n"
        return PushPreparation(self, intent, scan, capability, stdin_text, lock_path, lock_fd, pre_state)

    def _complete_push(
        self,
        preparation: PushPreparation,
        authorize: Callable[[GovernedPushCapability, str], PushAuthorization] | None = None,
    ) -> TransferOutcome:
        if preparation._finished:
            return TransferOutcome("DENY", PUSH_FAILED, "push preparation was already completed")
        authorizer = authorize or self._push_authority.authorize
        authorization = authorizer(preparation.capability, preparation.stdin_text)
        if authorization.decision != "ALLOW":
            self._finish_preparation(preparation)
            return TransferOutcome("DENY", authorization.code, authorization.reason)
        arguments = _secondary_network_arguments("push") + [
            "push",
            self._approved_remote.canonical_push_url,
            preparation.intent.exact_refspec,
        ]
        result = self._run(arguments)
        self._finish_preparation(preparation)
        if result is None or result.returncode != 0:
            return TransferOutcome("DENY", PUSH_FAILED, self._failure_detail(result))
        verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state = self._capture_repository_state(verified_at, preparation.intent.digest())
        if state is None:
            return TransferOutcome("DENY", TRANSFER_ENVIRONMENT_DRIFT, "post-transfer repository state is unavailable", None, None)
        differences = tuple(
            difference
            for difference in compare_repository_state(preparation.pre_state, state)
            if difference != "refs-changed"
        )
        if differences:
            return TransferOutcome("DENY", TRANSFER_ENVIRONMENT_DRIFT, "transfer environment changed mid-push: " + ", ".join(differences), None, state)
        return TransferOutcome("ALLOW", "OK", "governed push completed", None, state)

    def _abort_push(self, preparation: PushPreparation) -> None:
        self._finish_preparation(preparation)

    def _finish_preparation(self, preparation: PushPreparation) -> None:
        if preparation._finished:
            return
        preparation._finished = True
        self._release_push_lock(preparation.lock_path, preparation._lock_fd)

    def _sensitive_network_error(self) -> tuple[str, str] | None:
        if self._classification not in SENSITIVE_CLASSES:
            return None
        config = self._run(["config", "--local", "--null", "--list"])
        if config is None or config.returncode != 0:
            return (SECONDARY_NETWORK_DENIED, "repository configuration is unreadable")
        for entry in config.stdout.split(b"\x00"):
            if not entry:
                continue
            key = entry.split(b"\n", 1)[0].decode("utf-8", "replace").lower()
            if key == "extensions.partialclone" or key.endswith(".promisor") or key.endswith(".partialclonefilter"):
                return (SECONDARY_NETWORK_DENIED, "partial/promisor repository; lazy fetch is denied")
            if key.startswith("lfs.") or key.startswith("filter.lfs."):
                return (LFS_NETWORK_DENIED, "Git LFS configuration is present; LFS network is denied")
            if key.startswith("submodule."):
                return (SUBMODULE_NETWORK_DENIED, "submodule configuration is present; sensitive submodule network is denied")
        if (self._repository / ".lfsconfig").is_file():
            return (LFS_NETWORK_DENIED, ".lfsconfig is present; LFS network is denied")
        if (self._repository / ".gitmodules").is_file():
            return (SUBMODULE_NETWORK_DENIED, ".gitmodules is present; sensitive submodule network is denied")
        declared = self._declared_remotes()
        if declared is None:
            return (SECONDARY_NETWORK_DENIED, "repository remotes are unreadable")
        unapproved = unapproved_remotes(declared, (self._approved_remote,))
        if unapproved:
            return (UNAPPROVED_REMOTES_DENIED, "repository declares unapproved remotes: " + ", ".join(unapproved))
        return None

    def _declared_remotes(self) -> dict[str, list[str]] | None:
        result = self._run(["remote", "-v"])
        if result is None or result.returncode != 0:
            return None
        declared: dict[str, list[str]] = {}
        for line in result.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2] in {"(fetch)", "(push)"}:
                declared.setdefault(parts[0], []).append(parts[1])
        return declared

    def _push_lock_path(self) -> Path | None:
        result = self._run(["rev-parse", "--path-format=absolute", "--git-common-dir"])
        if result is None or result.returncode != 0:
            return None
        return Path(result.stdout.strip().decode("utf-8", "replace")) / "ainative-push.lock"

    def _acquire_push_lock(self) -> tuple[Path, int] | None:
        path = self._push_lock_path()
        if path is None:
            return None
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return None
        os.write(descriptor, f"{os.getpid()} {time.time()}\n".encode("ascii"))
        return path, descriptor

    def _release_push_lock(self, path: Path, descriptor: int) -> None:
        try:
            os.close(descriptor)
        except OSError:
            # WHY: a lock that cannot be removed fails closed; later pushes stay denied.
            pass
        try:
            os.unlink(path)
        except OSError:
            # WHY: see the close failure above; a remaining lock denies future pushes.
            pass

    def _capture_repository_state(self, verified_at: str, fetch_evidence_digest: str) -> LastVerifiedRepositoryState | None:
        refs_result = self._run(["for-each-ref", "--format=%(refname) %(objectname)"])
        index_result = self._run(["ls-files", "-s", "-z"])
        status_result = self._run(["status", "--porcelain=v1", "-z", "--untracked-files=no"])
        if refs_result is None or index_result is None or status_result is None:
            return None
        if refs_result.returncode or index_result.returncode or status_result.returncode:
            return None
        hooks_result = self._run(["rev-parse", "--git-path", "hooks"])
        if hooks_result is None or hooks_result.returncode != 0:
            return None
        refs = []
        for line in refs_result.stdout.decode("utf-8", "replace").splitlines():
            name, _separator, oid = line.partition(" ")
            if name and oid:
                refs.append((name, oid))
        remotes = []
        for url in (self._approved_remote.canonical_fetch_url, self._approved_remote.canonical_push_url):
            normalized = normalize_remote_url(url)
            if normalized:
                remotes.append(normalized)
        return LastVerifiedRepositoryState(
            approved_remotes=tuple(sorted(set(remotes))),
            refs=tuple(refs),
            index_tree_digest=sha256(index_result.stdout).hexdigest(),
            worktree_security_digest=sha256(status_result.stdout).hexdigest(),
            last_fetch_evidence_digest=fetch_evidence_digest,
            verified_at=verified_at,
            hooks_path_digest=sha256(hooks_result.stdout.strip()).hexdigest(),
        )

    @staticmethod
    def _failure_detail(result: subprocess.CompletedProcess[bytes] | None) -> str:
        if result is None:
            return "Git command failed to start or timed out"
        lines = result.stderr.decode("utf-8", "replace").strip().splitlines()
        return lines[-1] if lines else f"Git command exited with {result.returncode}"

    def _run(self, arguments: list[str]) -> subprocess.CompletedProcess[bytes] | None:
        try:
            return subprocess.run(
                [self._git, *arguments],
                cwd=str(self._repository),
                env=self._environment,
                capture_output=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None