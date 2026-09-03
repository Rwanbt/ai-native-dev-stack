"""PR-02 filesystem Work Controller with manifest-last commits."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
import secrets
import shutil
import socket
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .authorization import authorize_mutation
from .bootstrap import BootstrapError, admits, governs, read_creation_approval, verified_anchor
from .contracts import NORMATIVE_ARTIFACTS, ContractError, canonical_digest, validate_normative, canonical_json_bytes, canonical_path, digest_bytes, generate_uid, validate_artifact
from .provenance import UNOBSERVED, observe_artifacts
from .trust import approval_root_commitment, policy_commitment


class ControllerError(RuntimeError):
    """A failed controller operation; committed state remains authoritative."""


def process_is_alive(pid: int) -> bool:
    """Report whether a PID is running on this host.

    WHY: a recycled PID reads as alive and a permission error reads as alive.
    Both err toward refusing to reclaim a lock, which is the fail-closed side.
    """

    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    query_limited_information = 0x1000
    still_active = 259
    # WHY declare the signatures: without them ctypes marshals the returned
    # HANDLE as a 32-bit int, so a live process reads as dead and its lock
    # would be reclaimed underneath it.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


class WorkController:
    """Sole normative writer for one work directory."""

    def __init__(self, work_dir: str | os.PathLike[str], *, failure_injector: Callable[[str], None] | None = None):
        self.root = Path(work_dir)
        self.manifest_path = self.root / "manifest.json"
        self.revisions = self.root / "revisions"
        self.staging = self.root / ".staging"
        self.lock_path = self.root / ".controller.lock"
        self.failure_injector = failure_injector

    def _step(self, name: str) -> None:
        if self.failure_injector:
            self.failure_injector(name)

    def _lock(self) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            return self._acquire()
        except FileExistsError:
            pass
        if not self._reclaim_dead_lock():
            raise ControllerError("CONCURRENT_WRITER")
        try:
            return self._acquire()
        except FileExistsError as exc:
            raise ControllerError("CONCURRENT_WRITER") from exc

    def _acquire(self) -> int:
        handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        owner = {"pid": os.getpid(), "host": socket.gethostname(), "created_at": datetime.now(timezone.utc).isoformat(), "transaction_id": uuid.uuid4().hex}
        os.write(handle, canonical_json_bytes(owner))
        return handle

    def _reclaim_dead_lock(self) -> bool:
        """Reclaim only a lock this host owns whose writer no longer exists."""

        try:
            owner = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(owner["pid"])
            host = owner["host"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ControllerError("INVALID_LOCK") from exc
        # WHY: a writer on another machine cannot be observed from here, so age
        # alone never justifies breaking its lock.
        if host != socket.gethostname() or process_is_alive(pid):
            return False
        self.lock_path.unlink(missing_ok=True)
        return True

    def _unlock(self, handle: int) -> None:
        os.close(handle)
        self.lock_path.unlink(missing_ok=True)

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            raise ControllerError("NO_COMMITTED_STATE")
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            from .contracts import validate_artifact
            validate_artifact(manifest)
            self._validate_pointers(manifest)
            return manifest
        except (OSError, json.JSONDecodeError, ContractError) as exc:
            raise ControllerError("INVALID_COMMITTED_STATE") from exc

    def _validate_pointers(self, manifest: Mapping[str, Any]) -> None:
        for pointer in manifest["artifacts"].values():
            path = self.root / canonical_path(pointer["path"])
            if not path.is_file() or digest_bytes(path.read_bytes()) != pointer["digest"]:
                raise ControllerError("UNEXPECTED_MUTATION")

    def read(self) -> dict[str, Any]:
        return self._load_manifest()

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))
        try:
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        except OSError:
            pass

    def _commit(self, previous: dict[str, Any] | None, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        revision = 1 if previous is None else previous["revision"] + 1
        transaction = uuid.uuid4().hex
        stage = self.staging / transaction
        revision_dir = self.revisions / str(revision)
        stage.mkdir(parents=True)
        try:
            self._step("before_artifact_write")
            pointers: dict[str, dict[str, str]] = {}
            for name, value in artifacts.items():
                if not isinstance(name, str) or not name:
                    raise ControllerError("INVALID_ARTIFACT_NAME")
                normative = name in NORMATIVE_ARTIFACTS
                if normative:
                    try:
                        validate_normative(name, value)
                    except ContractError as error:
                        raise ControllerError(f"INVALID_NORMATIVE_ARTIFACT:{name}:{error.code}") from error
                elif isinstance(value, Mapping) and "schema_name" in value:
                    validate_artifact(value)
                filename = f"{name}.json"
                staged = stage / filename
                self._write_json(staged, value)
                pointers[name] = {"path": f"revisions/{revision}/{filename}", "digest": digest_bytes(staged.read_bytes()), "normative": normative}
                self._step("after_staged_file")
            revision_dir.parent.mkdir(parents=True, exist_ok=True)
            if revision_dir.exists():
                raise ControllerError("REVISION_ALREADY_EXISTS")
            shutil.move(str(stage), str(revision_dir))
            self._step("after_promotion_before_manifest")
            manifest = {"schema_name": "work_manifest", "schema_version": 1, "work_uid": previous["work_uid"] if previous else generate_uid("work"), "revision": revision, "artifacts": pointers, "root_chain": self._extend_root_chain(previous, artifacts, revision), "policy_chain": self._extend_policy_chain(previous, artifacts, revision)}
            temporary = self.root / f".manifest.{secrets.token_hex(8)}.tmp"
            self._write_json(temporary, manifest)
            self._step("before_manifest_replace")
            os.replace(temporary, self.manifest_path)
            self._step("after_manifest_commit")
            return manifest
        finally:
            if stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    @staticmethod
    def _extend_chain(previous: Mapping[str, Any] | None, revision: int, *, field: str, digest: str | None) -> list[dict[str, Any]]:
        """Append a commitment to a committed chain when it changes."""

        chain = [dict(entry) for entry in (previous.get(field, []) if previous else [])]
        if digest is None:
            return chain
        if not chain or chain[-1]["digest"] != digest:
            chain.append({"revision": revision, "digest": digest})
        return chain

    def _extend_policy_chain(self, previous: Mapping[str, Any] | None, artifacts: Mapping[str, Any], revision: int) -> list[dict[str, Any]]:
        """Carry the committed policy chain forward.

        WHY a chain and not just the current policy: a root transition has to be
        judged under the policy in force *when it happened*, or a later, weaker
        policy would retroactively authorize an old transition it never saw.
        Resolving historical policies needs them to be committed, and the
        manifest is what makes a revision committed.
        """

        policy = artifacts.get("project_policy")
        return self._extend_chain(previous, revision, field="policy_chain", digest=policy_commitment(policy) if isinstance(policy, Mapping) else None)

    @staticmethod
    def _extend_root_chain(previous: Mapping[str, Any] | None, artifacts: Mapping[str, Any], revision: int) -> list[dict[str, Any]]:
        """Carry the committed root chain forward, appending a rotation.

        WHY the chain lives in the manifest: the manifest is the commit marker.
        A revision directory can exist without ever having been committed --
        crash consistency permits exactly that -- so a root found by listing
        directories is not evidence that it was ever authoritative. A root
        recorded here was, because the atomic replace that recorded it is what
        makes a revision committed at all.
        """

        root = artifacts.get("approval_root")
        return WorkController._extend_chain(previous, revision, field="root_chain", digest=approval_root_commitment(root) if isinstance(root, Mapping) else None)

    def create(self, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        handle = self._lock()
        try:
            self._recover_interrupted()
            if self.manifest_path.exists():
                raise ControllerError("WORK_ALREADY_EXISTS")
            self._require_project_trust(artifacts)
            return self._commit(None, artifacts)
        finally:
            self._unlock(handle)

    def project_anchor(self) -> tuple[Path, dict[str, Any]] | None:
        """The verified project trust anchor governing this work, if any.

        Verified, not merely loaded: an anchor that no longer establishes
        anything must not authorize a write. The same function decides this for
        the evaluator, so the two cannot drift apart.
        """

        try:
            return verified_anchor(self.root)
        except BootstrapError as error:
            raise ControllerError(f"UNGOVERNED_PROJECT: {error}") from error

    def _require_project_trust(self, artifacts: Mapping[str, Any]) -> None:
        """Refuse a work that invents its own authority inside a governed project.

        Two questions, and the fifth review found only the first being asked:
        which root governs this work, and who admitted *this* initial contract.
        Requirements, acceptance criteria and specifications are success
        conditions, so revision 1 states what must be accomplished. Choosing
        that is proposing; an approval under project authority is what promotes
        the proposal.

        Where no anchor exists this permits the creation and establishes
        nothing: an ungoverned work directory is a local scratch, and the
        evaluator refuses to converge on one.
        """

        located = self.project_anchor()
        if located is None:
            return
        _, anchor = located
        refusal = governs(anchor, approval_root=artifacts.get("approval_root"))
        if refusal is not None:
            raise ControllerError(f"UNGOVERNED_GENESIS: {refusal}")
        approval, facts = read_creation_approval(self.root, anchor)
        refusal = admits(anchor, approval=approval, genesis_digest=self.normative_digest(artifacts), facts=facts)
        if refusal is not None:
            raise ControllerError(f"UNADMITTED_WORK: {refusal}")

    def mutate(self, expected_revision: int, set_artifacts: Mapping[str, Any] | None = None, *, delete_artifacts: Iterable[str] = (), approval: str | os.PathLike[str] | None = None) -> dict[str, Any]:
        """Apply an explicit change to the committed set.

        @contract Nothing disappears unless it is named in delete_artifacts.
        A revision is the previous set with the named artifacts replaced and
        the named artifacts removed, never only what the caller supplied.
        @contract A change to any normative artifact requires an approval that
        the policy of revision N authorizes for exactly this revision N+1, and
        `approval` is the *path* to that approval, not the object. The
        controller observes the artifact's own provenance, so an approval the
        caller merely constructed authorizes nothing: under a policy requiring
        `git_recorded` it must already be recorded, and under one requiring
        `signature_verified` an actor without the key cannot produce it.
        """

        handle = self._lock()
        try:
            self._recover_interrupted()
            current = self._load_manifest()
            if expected_revision != current["revision"]:
                raise ControllerError("STALE_REVISION")
            merged = self._read_artifacts(current)
            previous_artifacts = dict(merged)
            for name in delete_artifacts:
                if name not in merged:
                    raise ControllerError(f"UNKNOWN_ARTIFACT:{name}")
                del merged[name]
            merged.update(set_artifacts or {})
            if not merged:
                raise ControllerError("EMPTY_REVISION")
            self._require_authorization(current, previous_artifacts, merged, approval)
            return self._commit(current, merged)
        finally:
            self._unlock(handle)

    def policy_history(self) -> list[dict[str, Any]]:
        """Every policy this work actually committed, oldest first.

        @contract Only revisions named in the committed manifest policy chain
        are read, and each policy must still commit to what the chain recorded.
        """

        return self._committed_chain("policy_chain", "project_policy.json", policy_commitment)

    def root_history(self) -> list[dict[str, Any]]:
        """Every approval root this work actually committed, oldest first.

        A rotated root names a predecessor, and the predecessor is the root of
        an earlier revision of this work. Resolving it here is what lets the
        production path validate a chain instead of only a genesis root.

        @contract Only revisions named in the committed manifest root chain are
        read, and each root must still digest to what the chain recorded. A
        revision directory promoted by a write that never reached its manifest
        replace is not history, and is never returned.
        """

        return self._committed_chain("root_chain", "approval_root.json", approval_root_commitment)

    def _committed_chain(self, field: str, filename: str, commitment: Callable[[Mapping[str, Any]], str]) -> list[dict[str, Any]]:
        """Resolve one committed chain from the revisions the manifest names."""

        manifest = self._load_manifest()
        history: list[dict[str, Any]] = []
        for entry in manifest.get(field, []):
            candidate = self.revisions / str(entry["revision"]) / filename
            if not candidate.is_file():
                continue
            try:
                artifact = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(artifact, Mapping) or commitment(artifact) != entry["digest"]:
                continue
            history.append(dict(artifact))
        return history

    @staticmethod
    def _require_root_connectivity(before: Any, after: Any) -> None:
        """A new root must say which committed root it replaces.

        WHY: the chain invariant is that P0 authorizes P1 and P1 authorizes P2.
        A root that simply changes content and declares no predecessor is a
        second genesis inside an already governed work, and the fifth review
        found that `transition_approval` was therefore optional exactly where
        it decides something. Whether the transition is *authorized* is settled
        against observed facts in `trust._authorized_transition`; what is
        settled here is that it was even claimed.
        """

        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            return
        if approval_root_commitment(after) == approval_root_commitment(before):
            return
        predecessor = after.get("predecessor")
        if not isinstance(predecessor, Mapping):
            raise ControllerError("UNAUTHORIZED_MUTATION: a new approval root must name the committed root it replaces as its predecessor")
        if predecessor.get("uid") != before.get("uid") or predecessor.get("digest") != before.get("root_digest"):
            raise ControllerError("UNAUTHORIZED_MUTATION: the new approval root names a predecessor that is not the committed root")
        if not isinstance(after.get("transition_approval"), Mapping):
            raise ControllerError("UNAUTHORIZED_MUTATION: a root transition carries no transition approval")

    def genesis_normative_digest(self) -> str | None:
        """The normative digest of revision 1, recomputed from what it committed.

        Recomputed rather than remembered: a field in the current manifest
        would be a claim by whoever last wrote the manifest, and the question
        is what the project actually admitted.
        """

        genesis = self.revisions / "1"
        if not genesis.is_dir():
            return None
        artifacts: dict[str, Any] = {}
        for name in sorted(NORMATIVE_ARTIFACTS):
            candidate = genesis / f"{name}.json"
            if not candidate.is_file():
                continue
            try:
                artifacts[name] = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return self.normative_digest(artifacts)

    def normative_digest(self, artifacts: Mapping[str, Any]) -> str:
        """Digest exactly the artifacts that decide what success means."""

        return canonical_digest({name: artifacts[name] for name in sorted(NORMATIVE_ARTIFACTS) if name in artifacts})

    def authority_paths(self, manifest: Mapping[str, Any]) -> list[Path]:
        """The manifest and the normative artifacts it points at."""

        paths = [self.manifest_path]
        for pointer in manifest["artifacts"].values():
            if pointer.get("normative"):
                paths.append(self.root / canonical_path(pointer["path"]))
        return paths

    def _require_authorization(self, manifest: Mapping[str, Any], previous: Mapping[str, Any], candidate: Mapping[str, Any], approval: str | os.PathLike[str] | None) -> None:
        """Refuse a change to the success conditions that nobody authorized."""

        before = {name: value for name, value in previous.items() if name in NORMATIVE_ARTIFACTS}
        after = {name: value for name, value in candidate.items() if name in NORMATIVE_ARTIFACTS}
        if before == after:
            return
        self._require_root_connectivity(before.get("approval_root"), after.get("approval_root"))
        record, facts = self._read_approval(approval)
        refusal = authorize_mutation(
            record,
            policy=previous.get("project_policy"),
            candidate_digest=self.normative_digest(candidate),
            facts=facts,
        )
        if refusal is not None:
            raise ControllerError(f"UNAUTHORIZED_MUTATION: {refusal}")

    def _read_approval(self, approval: str | os.PathLike[str] | None) -> tuple[Any, Any]:
        """Load an approval and observe the artifact it actually is.

        WHY a path and not an object: an in-memory mapping carries no
        provenance of its own, so checking it against the *previous* state's
        provenance only proves the previous state was clean. The approval has
        to be a thing that exists, so that what is required of it can be
        established about it.
        """

        if approval is None:
            return None, UNOBSERVED
        if not isinstance(approval, (str, os.PathLike)):
            raise ControllerError("UNAUTHORIZED_MUTATION: an approval must be a recorded artifact, not an object")
        path = Path(approval)
        if not path.is_file():
            raise ControllerError("UNAUTHORIZED_MUTATION: the approval is not a readable artifact")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ControllerError("UNAUTHORIZED_MUTATION: the approval could not be read") from error
        # Reading the anchor here also verifies it: an approval measured against
        # the signer set of an anchor nobody can rely on establishes nothing.
        located = self.project_anchor()
        signers = located[1]["authorized_signers"] if located else None
        return record, observe_artifacts([path], authorized_signers=signers)

    def _read_artifacts(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Load the artifacts a validated manifest points at."""

        artifacts: dict[str, Any] = {}
        for name, pointer in manifest["artifacts"].items():
            path = self.root / canonical_path(pointer["path"])
            try:
                artifacts[name] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ControllerError("INVALID_COMMITTED_STATE") from error
        return artifacts

    def load_committed_artifacts(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return the validated manifest and the exact committed artifact set.

        @contract Every pointer is digest-checked before its artifact is read,
        and every normative artifact is validated against its schema, so a
        caller cannot receive committed state the controller would refuse to
        write today.
        """

        manifest = self._load_manifest()
        artifacts = self._read_artifacts(manifest)
        for name, value in artifacts.items():
            if name in NORMATIVE_ARTIFACTS:
                try:
                    validate_normative(name, value)
                except ContractError as error:
                    raise ControllerError(f"INVALID_NORMATIVE_ARTIFACT:{name}:{error.code}") from error
        return manifest, artifacts

    def recover_staging(self) -> int:
        handle = self._lock()
        try:
            return self._recover_interrupted()
        finally:
            self._unlock(handle)

    def _recover_interrupted(self) -> int:
        """Discard files that cannot be authoritative without a matching manifest."""

        removed = 0
        if self.staging.exists():
            for child in self.staging.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                    removed += 1
        for temporary in self.root.glob(".manifest.*.tmp"):
            temporary.unlink(missing_ok=True)
            removed += 1
        committed_revision = 0
        if self.manifest_path.exists():
            committed_revision = self._load_manifest()["revision"]
        if self.revisions.exists():
            for child in self.revisions.iterdir():
                if child.is_dir() and child.name.isdigit() and int(child.name) > committed_revision:
                    shutil.rmtree(child)
                    removed += 1
        return removed
