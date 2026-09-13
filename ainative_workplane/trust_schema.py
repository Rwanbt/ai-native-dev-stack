"""The shapes trust onboarding produces, validated before anything consumes them.

The approval root and the policy were implicit structures: `bootstrap()` read
them with `approval_root["uid"]`, so an empty `{}` produced a `KeyError`
traceback and exit 1 (which the Work Plane contract reserves for
NOT_CONVERGED). The only complete examples lived in test fixtures and the
dogfood script, so a user had to reverse-engineer two JSON documents to use a
profile sold for teams.

This module is the single source of truth for both shapes:

* `validate_approval_root` and `validate_policy` raise `TrustSchemaError` with
  the stable codes `TRUST_ROOT_INVALID`, `TRUST_POLICY_INVALID` or
  `TRUST_SCHEMA_UNSUPPORTED` - never a bare `KeyError`;
* `scaffold_policy` and `scaffold_approval_root` produce a minimal, coherent,
  *untrusted* pair: writing them establishes nothing until the explicit
  `trust bootstrap` ceremony runs. Scaffolding is not authority.

Validation goes through `contracts.validate_artifact`, so the structural rules
(uid grammar, digest shape, provenance values, schema versions) have exactly
one owner; this module adds the semantic coherence the schema cannot see: the
self-commitments, the predicate vocabulary and the predicate agreement between
the policy and the bootstrap act.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from .contracts import ContractError, generate_uid, validate_artifact
from .predicates import predicate_requirements
from .provenance import OBSERVABLE_FACTS
from .trust import approval_root_commitment, policy_commitment

ROOT_CODE = "TRUST_ROOT_INVALID"
POLICY_CODE = "TRUST_POLICY_INVALID"
UNSUPPORTED_CODE = "TRUST_SCHEMA_UNSUPPORTED"

SUPPORTED_SCHEMA_VERSION = 1
DEFAULT_PREDICATE = "recorded_owner_ack"
SCAFFOLD_PROVENANCE = "GIT_RECORDED"


class TrustSchemaError(RuntimeError):
    """A refusal carrying a stable code the CLI prints and scripts parse."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_UNSUPPORTED_CONTRACT_CODES = ("UNSUPPORTED_SCHEMA", "UNSUPPORTED_SCHEMA_VERSION")


def _translate(error: ContractError, code: str, label: str) -> TrustSchemaError:
    stable = UNSUPPORTED_CODE if error.code in _UNSUPPORTED_CONTRACT_CODES else code
    return TrustSchemaError(stable, f"{label}: {error}")


def _require_present(document: Any, label: str, code: str) -> Mapping[str, Any]:
    if not isinstance(document, Mapping):
        raise TrustSchemaError(code, f"{label} must be a JSON object")
    return document


def validate_approval_root(document: Any) -> Mapping[str, Any]:
    """The root document, or `TRUST_ROOT_INVALID` / `TRUST_SCHEMA_UNSUPPORTED`."""

    root = _require_present(document, "approval root", ROOT_CODE)
    name = root.get("schema_name")
    if name is None:
        raise TrustSchemaError(ROOT_CODE, "approval root declares no schema_name")
    if name != "approval_root":
        raise TrustSchemaError(
            UNSUPPORTED_CODE,
            f"approval root declares schema_name {name!r}; expected 'approval_root'")
    try:
        validate_artifact(dict(root))
    except ContractError as error:
        raise _translate(error, ROOT_CODE, "approval root") from error
    if root.get("root_digest") != approval_root_commitment(root):
        raise TrustSchemaError(
            ROOT_CODE,
            "root_digest does not commit to the document's content; regenerate it "
            "with `ainative trust init`")
    return root


def validate_policy(document: Any) -> Mapping[str, Any]:
    """The policy document, or `TRUST_POLICY_INVALID` / `TRUST_SCHEMA_UNSUPPORTED`."""

    policy = _require_present(document, "policy", POLICY_CODE)
    name = policy.get("schema_name")
    if name is None:
        raise TrustSchemaError(POLICY_CODE, "policy declares no schema_name")
    if name != "project_policy":
        raise TrustSchemaError(
            UNSUPPORTED_CODE,
            f"policy declares schema_name {name!r}; expected 'project_policy'")
    try:
        validate_artifact(dict(policy))
    except ContractError as error:
        raise _translate(error, POLICY_CODE, "policy") from error

    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        predicate_id = policy[field].get("predicate_id")
        if predicate_requirements(predicate_id) is None:
            raise TrustSchemaError(
                POLICY_CODE,
                f"{field}.predicate_id {predicate_id!r} names no known predicate; "
                "known: " + ", ".join(sorted(
                    candidate for candidate in
                    ("signature", "git_review", "ci_attestation", "recorded_owner_ack"))))
    for field in ("required_mutation_facts", "required_evidence_facts"):
        unknown = [fact for fact in policy[field] if fact not in OBSERVABLE_FACTS]
        if unknown:
            raise TrustSchemaError(
                POLICY_CODE, f"{field} names facts the runtime cannot observe: "
                             + ", ".join(sorted(unknown)))

    if not _policy_digests_match(policy):
        raise TrustSchemaError(
            POLICY_CODE,
            "policy_digest fields do not commit to the document's content; "
            "regenerate them with `ainative trust init`")
    return policy


def _policy_digests_match(policy: Mapping[str, Any]) -> bool:
    commitment = policy_commitment(policy)
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        if policy[field].get("policy_digest") != commitment:
            return False
    return True


def require_matching_predicate(policy: Mapping[str, Any], predicate_id: str) -> None:
    """The anchor records one predicate; the policy configures one. They agree."""

    configured = policy["approval_predicate"].get("predicate_id")
    if configured != predicate_id:
        raise TrustSchemaError(
            POLICY_CODE,
            f"--predicate {predicate_id!r} does not match the policy's "
            f"approval_predicate {configured!r}; bootstrap the predicate the "
            "policy actually configures")


def scaffold_policy(*, predicate_id: str = DEFAULT_PREDICATE,
                    required_facts: Mapping[str, bool] | None = None,
                    promotion_policy: str = "explicit") -> dict[str, Any]:
    """A minimal coherent policy. Nothing here is authority until bootstrap."""

    if predicate_requirements(predicate_id) is None:
        raise TrustSchemaError(
            UNSUPPORTED_CODE,
            f"predicate {predicate_id!r} names no known predicate; known: "
            "signature, git_review, ci_attestation, recorded_owner_ack")
    facts = dict(required_facts or {"git_recorded": True})
    unknown = [fact for fact in facts if fact not in OBSERVABLE_FACTS]
    if unknown:
        raise TrustSchemaError(UNSUPPORTED_CODE,
                               "required facts the runtime cannot observe: "
                               + ", ".join(sorted(unknown)))
    placeholder = "0" * 64
    policy: dict[str, Any] = {
        "schema_name": "project_policy",
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "approval_predicate": {"predicate_id": predicate_id, "policy_digest": placeholder},
        "required_mutation_facts": dict(facts),
        "required_evidence_facts": dict(facts),
        "waiver_approval_rule": {"predicate_id": predicate_id, "policy_digest": placeholder},
        "human_approval_rule": {"predicate_id": predicate_id, "policy_digest": placeholder},
        "promotion_policy": promotion_policy,
    }
    commitment = policy_commitment(policy)
    for field in ("approval_predicate", "waiver_approval_rule", "human_approval_rule"):
        policy[field]["policy_digest"] = commitment
    return policy


def scaffold_approval_root(policy: Mapping[str, Any], *, initialized_by: str,
                           provenance: str = SCAFFOLD_PROVENANCE) -> dict[str, Any]:
    """A minimal coherent root. `initialized_by` is a name, not a proof."""

    root: dict[str, Any] = {
        "schema_name": "approval_root",
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "uid": generate_uid("root"),
        "root_digest": "0" * 64,
        "policy_digest": policy_commitment(policy),
        "root_provenance": provenance,
        "bootstrap": {"initialized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "initialized_by": initialized_by},
    }
    root["root_digest"] = approval_root_commitment(root)
    return root


__all__ = ["TrustSchemaError", "ROOT_CODE", "POLICY_CODE", "UNSUPPORTED_CODE",
           "SUPPORTED_SCHEMA_VERSION", "DEFAULT_PREDICATE",
           "validate_approval_root", "validate_policy", "require_matching_predicate",
           "scaffold_policy", "scaffold_approval_root"]