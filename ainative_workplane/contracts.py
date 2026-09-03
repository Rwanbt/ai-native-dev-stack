"""PR-01 schema contracts, canonicalization, and identity primitives.

The module validates portable data shapes only. It intentionally does not read
repositories, evaluate approvals, execute commands, or mutate manifests.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = {
    "work_manifest": {SCHEMA_VERSION},
    "requirements": {SCHEMA_VERSION},
    "acceptance_criteria": {SCHEMA_VERSION},
    "tasks": {SCHEMA_VERSION},
    "verification_specification": {SCHEMA_VERSION},
    "project_policy": {SCHEMA_VERSION},
    "approval_root": {SCHEMA_VERSION},
    "waiver": {SCHEMA_VERSION},
    "human_approval": {SCHEMA_VERSION},
    "repository_snapshot": {SCHEMA_VERSION},
    "verification_run": {SCHEMA_VERSION},
    "convergence_run": {SCHEMA_VERSION},
    "mutation_approval": {SCHEMA_VERSION},
    "command_registry": {SCHEMA_VERSION},
    "project_trust": {SCHEMA_VERSION},
    "work_creation_approval": {SCHEMA_VERSION},
}

# Artifact names the engine reads as authority. Anything committed under one
# of these names must be a valid artifact of the matching schema; anything
# committed under another name is stored, marked non-normative, and never read
# by the evaluator.
# Plural names hold a list of artifacts of the matching schema; singular names
# hold one. The distinction is what lets a work directory carry a whole
# contract without inventing a wrapper schema.
COLLECTION_ARTIFACTS = {
    "requirements": "requirements",
    "acceptance_criteria": "acceptance_criteria",
    "tasks": "tasks",
    "verification_specifications": "verification_specification",
    "waivers": "waiver",
    "human_approvals": "human_approval",
}

SINGLE_ARTIFACTS = {
    "project_policy": "project_policy",
    "approval_root": "approval_root",
    "command_registry": "command_registry",
}

NORMATIVE_ARTIFACTS = frozenset(COLLECTION_ARTIFACTS) | frozenset(SINGLE_ARTIFACTS)


def validate_normative(name: str, value: Any) -> None:
    """Validate one committed artifact against the schema its name implies."""

    if name in COLLECTION_ARTIFACTS:
        expected = COLLECTION_ARTIFACTS[name]
        if not isinstance(value, list):
            _fail("INVALID_FIELD", f"{name} must be a list of {expected} artifacts")
        for item in value:
            validate_artifact(item)
            if item.get("schema_name") != expected:
                _fail("UNSUPPORTED_SCHEMA", f"{name} may only contain {expected} artifacts")
        return
    validate_artifact(value)
    if value.get("schema_name") != SINGLE_ARTIFACTS[name]:
        _fail("UNSUPPORTED_SCHEMA", f"{name} must be a {SINGLE_ARTIFACTS[name]} artifact")

RELATIONSHIP_MODES = frozenset({"direct_scope", "black_box", "external_artifact", "human_approval"})
# Kept as descriptive metadata on artifacts. Nothing compares these strings
# any more: a claim is not a proof, and these four properties are independent
# rather than ranked. See ainative_workplane/provenance.py.
PROVENANCE_VALUES = frozenset({"UNTRACKED", "GIT_DIRTY", "GIT_RECORDED", "GIT_REVIEWED", "CI_APPROVED", "SIGNED", "LOCAL_UNTRUSTED"})
OBSERVABLE_FACTS = ("git_recorded", "git_reviewed", "ci_verified", "signature_verified")
EFFECTIVE_WAIVER_STATES = frozenset({"effective", "expired", "revoked"})
UID_PREFIXES = frozenset({"work", "req", "ac", "task", "verify", "run", "gap", "waiver", "approval", "root", "snapshot", "convergence", "trust"})
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_UID = re.compile(r"^(?P<prefix>[a-z]+)_(?P<body>[0-9A-HJKMNP-TV-Z]{26})$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class ContractError(ValueError):
    """A deterministic invalid-contract result suitable for a later runtime.

    WHY not a frozen dataclass: Python assigns __traceback__ on an exception
    as it propagates, and a frozen instance refuses that assignment, which
    breaks any runner that inspects the raised error.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _fail(code: str, message: str) -> None:
    raise ContractError(code, message)


def _normalise(value: Any) -> Any:
    if isinstance(value, float):
        _fail("FLOAT_NOT_ALLOWED", "normative JSON does not permit floating-point values")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                _fail("INVALID_JSON_KEY", "object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in result:
                _fail("NORMALIZATION_COLLISION", f"object keys collide after NFC normalization: {normalized_key!r}")
            result[normalized_key] = _normalise(child)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_normalise(child) for child in value]
    _fail("INVALID_JSON_VALUE", f"unsupported normative JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the NFC-normalized, whitespace-free UTF-8 representation."""

    normalized = _normalise(value)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def digest_bytes(content: bytes) -> str:
    """Digest file content without assigning filesystem collection semantics."""

    return hashlib.sha256(content).hexdigest()


def _encode_ulid(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    characters = ["0"] * 26
    for index in range(25, -1, -1):
        characters[index] = _CROCKFORD[number & 31]
        number >>= 5
    return "".join(characters)


def generate_uid(prefix: str, *, timestamp_ms: int | None = None, entropy: bytes | None = None) -> str:
    """Generate a prefixed ULID; the opaque UID, not a display ID, is authoritative."""

    if prefix not in UID_PREFIXES:
        _fail("INVALID_UID_PREFIX", f"unknown UID prefix: {prefix}")
    timestamp = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if timestamp < 0 or timestamp >= 1 << 48:
        _fail("INVALID_UID_TIMESTAMP", "ULID timestamp must fit 48 bits")
    randomness = secrets.token_bytes(10) if entropy is None else entropy
    if len(randomness) != 10:
        _fail("INVALID_UID_ENTROPY", "ULID entropy must contain exactly 10 bytes")
    return f"{prefix}_{_encode_ulid(timestamp.to_bytes(6, 'big') + randomness)}"


def validate_uid(value: Any, expected_prefix: str | None = None) -> str:
    if not isinstance(value, str):
        _fail("INVALID_UID", "uid must be a prefixed ULID string")
    match = _UID.fullmatch(value)
    if not match or match.group("prefix") not in UID_PREFIXES:
        _fail("INVALID_UID", f"invalid prefixed ULID: {value!r}")
    if expected_prefix and match.group("prefix") != expected_prefix:
        _fail("INVALID_UID", f"expected {expected_prefix}_ UID, got {value!r}")
    return value


def canonical_path(path: Any) -> str:
    """Canonicalize a repository-relative path without resolving the filesystem.

    A dot *component* is rejected. Dotfiles remain legal (for example .github).
    Symlink containment is a later collection/runtime responsibility.
    """

    if not isinstance(path, str) or not path:
        _fail("INVALID_PATH", "path must be a non-empty repository-relative string")
    normalized = unicodedata.normalize("NFC", path).replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//") or _WINDOWS_ABSOLUTE.match(normalized):
        _fail("INVALID_PATH", f"absolute path is forbidden: {path!r}")
    components = normalized.split("/")
    if any(component in {"", ".", ".."} for component in components):
        _fail("INVALID_PATH", f"path has empty, '.' or '..' component: {path!r}")
    return "/".join(components)


def validate_case_collisions(paths: Sequence[str]) -> tuple[str, ...]:
    canonical = tuple(canonical_path(path) for path in paths)
    seen: dict[str, str] = {}
    for path in canonical:
        folded = path.casefold()
        prior = seen.get(folded)
        if prior is not None and prior != path:
            _fail("CASE_COLLISION", f"paths collide on case-insensitive filesystems: {prior!r}, {path!r}")
        seen[folded] = path
    return canonical


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_FIELD", f"{field} must be an object")
    return value


def _list(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail("INVALID_FIELD", f"{field} must be an array")
    return value


def _required(value: Mapping[str, Any], field: str) -> Any:
    if field not in value:
        _fail("MISSING_REQUIRED_FIELD", f"missing required field: {field}")
    return value[field]


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        _fail("INVALID_DIGEST", f"{field} must be a lowercase SHA-256 digest")
    return value


def _provenance(value: Any, field: str) -> str:
    if value not in PROVENANCE_VALUES:
        _fail("INVALID_PROVENANCE", f"{field} must be a known provenance value")
    return value


def _reference(value: Any, field: str, prefix: str | None = None) -> Mapping[str, Any]:
    reference = _mapping(value, field)
    validate_uid(_required(reference, "uid"), prefix)
    _digest(_required(reference, "digest"), f"{field}.digest")
    return reference


def _schema_header(value: Mapping[str, Any], expected: str) -> None:
    if _required(value, "schema_name") != expected:
        _fail("INVALID_SCHEMA_NAME", f"expected schema_name {expected!r}")
    version = _required(value, "schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version not in SUPPORTED_SCHEMA_VERSIONS[expected]:
        _fail("UNSUPPORTED_SCHEMA_VERSION", f"unsupported required schema version for {expected}: {version!r}")


def _uid_field(value: Mapping[str, Any], prefix: str) -> None:
    validate_uid(_required(value, "uid"), prefix)


def _paths(value: Any, field: str) -> tuple[str, ...]:
    return validate_case_collisions([canonical_path(path) for path in _list(value, field)])


def _predicate_reference(value: Any, field: str) -> Mapping[str, Any]:
    predicate = _mapping(value, field)
    if not isinstance(_required(predicate, "predicate_id"), str) or not predicate["predicate_id"]:
        _fail("INVALID_PREDICATE", f"{field}.predicate_id must be non-empty")
    _digest(_required(predicate, "policy_digest"), f"{field}.policy_digest")
    return predicate


def _validate_work_manifest(value: Mapping[str, Any]) -> None:
    validate_uid(_required(value, "work_uid"), "work")
    revision = _required(value, "revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        _fail("INVALID_FIELD", "revision must be a positive integer")
    artifacts = _mapping(_required(value, "artifacts"), "artifacts")
    for name, reference in artifacts.items():
        if not isinstance(name, str):
            _fail("INVALID_FIELD", "artifact names must be strings")
        pointer = _mapping(reference, f"artifacts.{name}")
        path = _required(pointer, "path")
        canonical_path(path)
        _digest(_required(pointer, "digest"), f"artifacts.{name}.digest")
    if "approval_root" in value:
        _reference(value["approval_root"], "approval_root", "root")
    # The committed root and policy chains. Every entry names a revision whose
    # manifest was actually replaced, which is what stops a revision directory
    # left behind by a crash from being read as historical authority -- and what
    # lets a historical transition be judged under the policy in force then.
    for field in ("root_chain", "policy_chain"):
        for entry in _list(_required(value, field), field):
            link = _mapping(entry, f"{field}[]")
            revision = _required(link, "revision")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
                _fail("INVALID_FIELD", f"{field}[].revision must be a positive integer")
            _digest(_required(link, "digest"), f"{field}[].digest")
            if "authority" in link:
                # What the controller observed when it authorized this
                # transition, so the chain can be re-checked rather than
                # re-narrated against today's authority. See ADR-0007.
                evidence = _mapping(link["authority"], f"{field}[].authority")
                if not isinstance(_required(evidence, "commit"), str) or not evidence["commit"]:
                    _fail("INVALID_FIELD", f"{field}[].authority.commit must be non-empty")
                _digest(_required(evidence, "approval_digest"), f"{field}[].authority.approval_digest")


def _validate_requirements(value: Mapping[str, Any]) -> None:
    _uid_field(value, "req")
    if not isinstance(_required(value, "statement"), str) or not value["statement"]:
        _fail("INVALID_FIELD", "statement must be non-empty")
    for reference in _list(_required(value, "acceptance_criteria"), "acceptance_criteria"):
        _reference(reference, "acceptance_criteria[]", "ac")


def _validate_acceptance_criteria(value: Mapping[str, Any]) -> None:
    _uid_field(value, "ac")
    _reference(_required(value, "requirement"), "requirement", "req")
    if not isinstance(_required(value, "criterion"), str) or not value["criterion"]:
        _fail("INVALID_FIELD", "criterion must be non-empty")
    for reference in _list(_required(value, "verification_specifications"), "verification_specifications"):
        _reference(reference, "verification_specifications[]", "verify")
    if "human_approval" in value:
        _reference(value["human_approval"], "human_approval", "approval")


def _validate_tasks(value: Mapping[str, Any]) -> None:
    _uid_field(value, "task")
    for reference in _list(_required(value, "requirements"), "requirements"):
        _reference(reference, "requirements[]", "req")
    _paths(_required(value, "implementation_paths"), "implementation_paths")
    if "status" in value and value["status"] not in {"planned", "in_progress", "complete", "blocked"}:
        _fail("INVALID_ENUM", "status is not a supported normative metadata value")


def _validate_verification_specification(value: Mapping[str, Any]) -> None:
    _uid_field(value, "verify")
    for reference in _list(_required(value, "acceptance_criteria"), "acceptance_criteria"):
        _reference(reference, "acceptance_criteria[]", "ac")
    _reference(_required(value, "command_registry"), "command_registry")
    relationship = _required(value, "relationship")
    if relationship not in RELATIONSHIP_MODES:
        _fail("INVALID_VERIFICATION_RELATIONSHIP", "relationship must be a closed V2 relationship enum")
    _paths(_required(value, "execution_scope"), "execution_scope")
    covered_paths = _paths(_required(value, "covered_implementation_paths"), "covered_implementation_paths")
    dependencies = _list(_required(value, "dependencies"), "dependencies")
    for dependency in dependencies:
        _reference(dependency, "dependencies[]")
    if relationship != "direct_scope" and not covered_paths and not dependencies:
        _fail("INSUFFICIENT_VERIFICATION_SCOPE", "non-direct verification requires covered paths or structured dependencies")
    if relationship == "human_approval":
        _predicate_reference(_required(value, "approval_predicate"), "approval_predicate")
    if not isinstance(_required(value, "substance_requirement"), str) or not value["substance_requirement"]:
        _fail("INVALID_FIELD", "substance_requirement must be non-empty")
    _provenance(_required(value, "required_evidence_provenance"), "required_evidence_provenance")


def _fact_requirement(value: Any, field: str) -> Mapping[str, Any]:
    """A policy states the properties it needs, each independently."""

    requirement = _mapping(value, field)
    for name, needed in requirement.items():
        if name not in OBSERVABLE_FACTS:
            _fail("UNKNOWN_PROVENANCE_FACT", f"{field}.{name} is not a fact the runtime can establish")
        if not isinstance(needed, bool):
            _fail("INVALID_FIELD", f"{field}.{name} must be a boolean")
    return requirement


def _validate_project_policy(value: Mapping[str, Any]) -> None:
    _predicate_reference(_required(value, "approval_predicate"), "approval_predicate")
    for field in ("required_mutation_facts", "required_evidence_facts"):
        _fact_requirement(_required(value, field), field)
    _predicate_reference(_required(value, "waiver_approval_rule"), "waiver_approval_rule")
    _predicate_reference(_required(value, "human_approval_rule"), "human_approval_rule")
    if not isinstance(_required(value, "promotion_policy"), str) or not value["promotion_policy"]:
        _fail("INVALID_FIELD", "promotion_policy must be non-empty")


def _validate_approval_root(value: Mapping[str, Any]) -> None:
    _uid_field(value, "root")
    _digest(_required(value, "root_digest"), "root_digest")
    _digest(_required(value, "policy_digest"), "policy_digest")
    _provenance(_required(value, "root_provenance"), "root_provenance")
    bootstrap = _mapping(_required(value, "bootstrap"), "bootstrap")
    if not isinstance(_required(bootstrap, "initialized_at"), str) or not isinstance(_required(bootstrap, "initialized_by"), str):
        _fail("INVALID_FIELD", "bootstrap metadata must include initialized_at and initialized_by")
    if "predecessor" in value:
        _reference(value["predecessor"], "predecessor", "root")
        approval = _mapping(_required(value, "transition_approval"), "transition_approval")
        if not isinstance(_required(approval, "predicate_id"), str) or not approval["predicate_id"]:
            _fail("INVALID_PREDICATE", "transition_approval.predicate_id must be non-empty")
        if not isinstance(_required(approval, "approved_by"), str) or not approval["approved_by"]:
            _fail("INVALID_FIELD", "transition_approval.approved_by must be non-empty")
        _provenance(_required(approval, "provenance"), "transition_approval.provenance")
        validate_uid(_required(approval, "successor_uid"), "root")
        _digest(_required(approval, "predecessor_digest"), "transition_approval.predecessor_digest")
        _digest(_required(approval, "successor_commitment"), "transition_approval.successor_commitment")
        _digest(_required(approval, "policy_digest"), "transition_approval.policy_digest")


def _validate_project_trust(value: Mapping[str, Any]) -> None:
    """The project-level anchor a work contract must already be governed by.

    It exists so that creating a work directory is not the act that decides
    what the project trusts. See ADR-0004.
    """

    _uid_field(value, "trust")
    _digest(_required(value, "trust_digest"), "trust_digest")
    _digest(_required(value, "policy_digest"), "policy_digest")
    _reference(_required(value, "approval_root"), "approval_root", "root")
    _predicate_reference(_required(value, "bootstrap_predicate"), "bootstrap_predicate")
    # The identities this project authorizes to satisfy a signature predicate.
    # Git verifying a signature says the signature is valid; it does not say the
    # signer may approve anything here. See ADR-0005.
    for identity in _list(_required(value, "authorized_signers"), "authorized_signers"):
        if not isinstance(identity, str) or not identity:
            _fail("INVALID_FIELD", "authorized_signers[] must be non-empty strings")
    bootstrap = _mapping(_required(value, "bootstrap"), "bootstrap")
    for field in ("initialized_at", "initialized_by"):
        if not isinstance(_required(bootstrap, field), str) or not bootstrap[field]:
            _fail("INVALID_FIELD", f"bootstrap.{field} must be non-empty")


def _validate_work_creation_approval(value: Mapping[str, Any]) -> None:
    """The record that project authority admitted one exact initial contract.

    Revision 1 states what must be accomplished, so it is a success condition
    like any other. Creating it is a proposal; this is what makes it authority.
    """

    _uid_field(value, "approval")
    validate_uid(_required(value, "trust_uid"), "trust")
    _digest(_required(value, "trust_digest"), "trust_digest")
    _digest(_required(value, "genesis_digest"), "genesis_digest")
    for field in ("predicate_id", "approved_by", "approved_at"):
        if not isinstance(_required(value, field), str) or not value[field]:
            _fail("INVALID_FIELD", f"{field} must be non-empty")


def _validate_command_registry(value: Mapping[str, Any]) -> None:
    """The trust base that decides what may execute.

    One validator, used both when the registry is committed and when the runner
    loads it, so the controller can never accept a registry the runner would
    refuse.
    """

    from .substance import SubstanceError, validate_contract as validate_substance

    commands = _mapping(_required(value, "commands"), "commands")
    if not commands:
        _fail("INVALID_COMMAND_REGISTRY", "a registry must declare at least one command")
    for name, definition in commands.items():
        if not isinstance(name, str) or not name:
            _fail("INVALID_COMMAND_REGISTRY", "command names must be non-empty strings")
        declared = _mapping(definition, f"commands.{name}")
        argv = _required(declared, "argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(argument, str) for argument in argv):
            _fail("INVALID_COMMAND_REGISTRY", f"commands.{name}.argv must be a non-empty list of strings")
        if declared.get("shell", False):
            _fail("SHELL_COMMAND_FORBIDDEN", f"commands.{name} may not request a shell")
        for field, minimum in (("timeout_seconds", 1), ("max_output_bytes", 1)):
            given = declared.get(field, minimum)
            if not isinstance(given, int) or isinstance(given, bool) or given < minimum:
                _fail("INVALID_COMMAND_REGISTRY", f"commands.{name}.{field} must be an integer >= {minimum}")
        if "substance" in declared:
            try:
                validate_substance(declared["substance"])
            except SubstanceError as error:
                _fail(str(error), f"commands.{name}.substance is not a usable contract")


def _validate_mutation_approval(value: Mapping[str, Any]) -> None:
    """The record that a previous authority accepted one exact next state."""

    _uid_field(value, "approval")
    _digest(_required(value, "target_digest"), "target_digest")
    # The state being left, not only the state being reached. Without it an
    # approval authorizes arriving somewhere rather than one transition, and an
    # old one replays to undo a later strengthening. See ADR-0007.
    _digest(_required(value, "base_digest"), "base_digest")
    _digest(_required(value, "policy_digest"), "policy_digest")
    for field in ("predicate_id", "approved_by", "approved_at"):
        if not isinstance(_required(value, field), str) or not value[field]:
            _fail("INVALID_FIELD", f"{field} must be non-empty")
    _provenance(_required(value, "provenance"), "provenance")


def _validate_waiver(value: Mapping[str, Any]) -> None:
    _uid_field(value, "waiver")
    _reference(_required(value, "target"), "target")
    for field in ("reason", "scope", "approved_by", "approved_at"):
        if not isinstance(_required(value, field), str) or not value[field]:
            _fail("INVALID_FIELD", f"{field} must be non-empty")
    state = _required(value, "state")
    if state not in {"proposed", *EFFECTIVE_WAIVER_STATES}:
        _fail("INVALID_ENUM", "waiver state is invalid")
    _provenance(_required(value, "approval_provenance"), "approval_provenance")
    _predicate_reference(_required(value, "approval_predicate"), "approval_predicate")
    _digest(_required(value, "policy_digest"), "policy_digest")
    if state in EFFECTIVE_WAIVER_STATES and value["approval_provenance"] in {"UNTRACKED", "GIT_DIRTY", "LOCAL_UNTRUSTED"}:
        _fail("INVALID_WAIVER_AUTHORITY", "an effective waiver requires trusted approval provenance")


def _validate_human_approval(value: Mapping[str, Any]) -> None:
    _uid_field(value, "approval")
    _reference(_required(value, "target"), "target")
    for field in ("approved_by", "approved_at"):
        if not isinstance(_required(value, field), str) or not value[field]:
            _fail("INVALID_FIELD", f"{field} must be non-empty")
    _provenance(_required(value, "approval_provenance"), "approval_provenance")
    _predicate_reference(_required(value, "approval_predicate"), "approval_predicate")
    _digest(_required(value, "policy_digest"), "policy_digest")
    if "approved" in value:
        _fail("INVALID_FIELD", "human approval evidence must not use an approved boolean")


def _validate_repository_snapshot(value: Mapping[str, Any]) -> None:
    _uid_field(value, "snapshot")
    if not isinstance(_required(value, "head"), str) or not value["head"]:
        _fail("INVALID_FIELD", "head must be non-empty")
    if not isinstance(_required(value, "dirty"), bool):
        _fail("INVALID_FIELD", "dirty must be boolean")
    _paths(_required(value, "scope"), "scope")
    _paths(_required(value, "dependency_paths"), "dependency_paths")
    for dependency in _list(_required(value, "dependencies"), "dependencies"):
        _reference(dependency, "dependencies[]")
    for field in ("content_digest", "dependency_digest", "command_registry_digest", "policy_digest"):
        _digest(_required(value, field), field)


def _validate_verification_run(value: Mapping[str, Any]) -> None:
    _uid_field(value, "run")
    _reference(_required(value, "work"), "work", "work")
    revision = _required(value, "contract_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        _fail("INVALID_FIELD", "contract_revision must be a positive integer")
    for field in ("contract_digest", "command_registry_digest", "policy_digest", "snapshot_content_digest", "snapshot_dependency_digest"):
        _digest(_required(value, field), field)
    _reference(_required(value, "verification_specification"), "verification_specification", "verify")
    _reference(_required(value, "approval_root"), "approval_root", "root")
    _reference(_required(value, "repository_snapshot"), "repository_snapshot", "snapshot")
    for field in ("producer", "producer_version", "result", "started_at", "finished_at", "substance_metadata", "command"):
        _required(value, field)
    if not isinstance(_required(value, "snapshot_head"), str) or not value["snapshot_head"]:
        _fail("INVALID_FIELD", "snapshot_head must be the non-empty checkout head the run observed")
    if value["result"] not in {"PASS", "FAIL", "TIMEOUT", "SUSPICIOUS_VERIFICATION"}:
        _fail("INVALID_ENUM", "verification result is invalid")
    exit_code = _required(value, "exit_code")
    if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
        _fail("INVALID_FIELD", "exit_code must be an integer or null")
    duration = _required(value, "duration_ms")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
        _fail("INVALID_FIELD", "duration_ms must be a non-negative integer")
    for field in ("stdout_digest", "stderr_digest"):
        _digest(_required(value, field), field)
    _provenance(_required(value, "evidence_provenance"), "evidence_provenance")


def _validate_convergence_run(value: Mapping[str, Any]) -> None:
    _uid_field(value, "convergence")
    _reference(_required(value, "work"), "work", "work")
    for field in ("policy_digest", "registry_digest"):
        _digest(_required(value, field), field)
    _reference(_required(value, "approval_root"), "approval_root", "root")
    _reference(_required(value, "snapshot"), "snapshot", "snapshot")
    for reference in _list(_required(value, "verification_runs"), "verification_runs"):
        _reference(reference, "verification_runs[]", "run")
    _list(_required(value, "gaps"), "gaps")
    for field in ("verdict", "timestamp", "engine_version"):
        _required(value, field)


_VALIDATORS = {
    "work_manifest": _validate_work_manifest,
    "requirements": _validate_requirements,
    "acceptance_criteria": _validate_acceptance_criteria,
    "tasks": _validate_tasks,
    "verification_specification": _validate_verification_specification,
    "project_policy": _validate_project_policy,
    "approval_root": _validate_approval_root,
    "command_registry": _validate_command_registry,
    "mutation_approval": _validate_mutation_approval,
    "waiver": _validate_waiver,
    "human_approval": _validate_human_approval,
    "repository_snapshot": _validate_repository_snapshot,
    "verification_run": _validate_verification_run,
    "convergence_run": _validate_convergence_run,
    "project_trust": _validate_project_trust,
    "work_creation_approval": _validate_work_creation_approval,
}


def validate_artifact(value: Any) -> None:
    """Validate a known schema-bearing V2 artifact without changing it."""

    artifact = _mapping(value, "artifact")
    name = _required(artifact, "schema_name")
    if name not in _VALIDATORS:
        _fail("UNSUPPORTED_SCHEMA", f"unsupported required schema: {name!r}")
    _schema_header(artifact, name)
    _VALIDATORS[name](artifact)
