"""Trust model (V3.3.1 erratum): approval authenticity, not capability.

Three orthogonal fields, never collapsed (S1): approval_mode (which
ceremony ran), capability_status (QUAL-T exposure result), and
evidence_status (whether the evidence is non-forgeably rooted). Only
VERIFIED_WORKPLANE_AUTHORITY and EXTERNALLY_ATTESTED evidence can be
production-trust-qualified (S11); TRUSTED_OPERATOR_CEREMONY always
pairs with UNVERIFIED_CEREMONY, even when separated (S3).

Verification itself is never reimplemented here: the authority check
arrives as an injected callback owning the existing Verified Work
Plane primitive (S5/S6/S19). Without a verifier, VERIFIED claims fail
closed (S15: no fallback to ceremony-trusted).
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Callable

from .errors import KnowledgeError

TRUSTED_OPERATOR_CEREMONY = "TRUSTED_OPERATOR_CEREMONY"
VERIFIED_WORKPLANE_AUTHORITY = "VERIFIED_WORKPLANE_AUTHORITY"
EXTERNAL_ATTESTATION = "EXTERNAL_ATTESTATION"

UNVERIFIED_CEREMONY = "UNVERIFIED_CEREMONY"
EXTERNALLY_ATTESTED = "EXTERNALLY_ATTESTED"

QUALIFIED_VERIFIED = "VERIFIED_WORKPLANE"
QUALIFIED_ATTESTED = "EXTERNALLY_ATTESTED"
QUALIFIED_UNVERIFIED = "UNVERIFIED"
QUALIFIED_INVALID = "INVALID"

HEALTHY = "HEALTHY"
REVERTED = "REVERTED"
SUPERSEDED = "SUPERSEDED"
MISSING = "MISSING"
AMBIGUOUS = "AMBIGUOUS"

MODES = frozenset({TRUSTED_OPERATOR_CEREMONY, VERIFIED_WORKPLANE_AUTHORITY,
                   EXTERNAL_ATTESTATION})
EVIDENCE_STATUSES = frozenset({UNVERIFIED_CEREMONY, VERIFIED_WORKPLANE_AUTHORITY,
                               EXTERNALLY_ATTESTED})
CAPABILITY_STATUSES = frozenset({"SEPARATED", "NOT_SEPARATED", "UNKNOWN"})


def approval_digest(*, decision_id: str, target: str, operation: str,
                    scope: dict, base_digest: str,
                    intended_result_digest: str,
                    assertion_hash: str | None = None) -> str:
    """The exact digest authority evidence must bind (S26). Pure function."""

    payload = {"decision_id": decision_id, "target": target,
               "operation": operation, "scope": scope,
               "base_digest": base_digest,
               "intended_result_digest": intended_result_digest,
               "assertion_hash": assertion_hash}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_receipt(*, mode: str, capability_status: str, evidence_status: str,
                  approval_digest_value: str,
                  authority_ref: str | None = None,
                  attestation_ref: str | None = None) -> dict[str, Any]:
    """One approval receipt. Ceremony can never claim verified evidence (S3)."""

    if mode not in MODES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED", f"unknown approval mode {mode!r}")
    if capability_status not in CAPABILITY_STATUSES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown capability status {capability_status!r}")
    if evidence_status not in EVIDENCE_STATUSES:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             f"unknown evidence status {evidence_status!r}")
    if mode == TRUSTED_OPERATOR_CEREMONY and evidence_status != UNVERIFIED_CEREMONY:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "ceremony evidence is always UNVERIFIED_CEREMONY (S3)")
    if evidence_status == VERIFIED_WORKPLANE_AUTHORITY and not authority_ref:
        raise KnowledgeError("KNOWLEDGE_MALFORMED",
                             "VERIFIED evidence needs authority_ref (S15)")
    return {"mode": mode, "capability_status": capability_status,
            "evidence_status": evidence_status,
            "approval_digest": approval_digest_value,
            "authority_ref": authority_ref, "attestation_ref": attestation_ref}


Verifier = Callable[[str, str], bool]


def derive_qualification(receipt: dict[str, Any], *,
                         verify: Verifier | None = None) -> str:
    """Trust qualification from a receipt (S11/S15/S20). No fallback (S15)."""

    evidence = receipt.get("evidence_status")
    if evidence == UNVERIFIED_CEREMONY:
        return QUALIFIED_UNVERIFIED
    if evidence == EXTERNALLY_ATTESTED:
        if receipt.get("attestation_ref"):
            return QUALIFIED_ATTESTED
        return QUALIFIED_INVALID
    if evidence == VERIFIED_WORKPLANE_AUTHORITY:
        reference = receipt.get("authority_ref")
        if not reference or verify is None:
            return QUALIFIED_INVALID
        try:
            return QUALIFIED_VERIFIED if verify(reference, receipt["approval_digest"]) \
                else QUALIFIED_INVALID
        except Exception:
            return QUALIFIED_INVALID
    return QUALIFIED_INVALID


def production_trust_qualified(qualification: str) -> bool:
    """Final rule (S11/S22): evidence-rooted only, never capability alone."""

    return qualification in (QUALIFIED_VERIFIED, QUALIFIED_ATTESTED)


def validate_receipt(receipt: dict[str, Any], *,
                     verify: Verifier | None = None) -> str:
    """Raise APPROVAL_AUTHORITY_INVALID on verified-claim failure (S15)."""

    qualification = derive_qualification(receipt, verify=verify)
    if (receipt.get("evidence_status") == VERIFIED_WORKPLANE_AUTHORITY
            and qualification != QUALIFIED_VERIFIED):
        raise KnowledgeError("KNOWLEDGE_APPROVAL_INVALID",
                             "authority_ref failed validation; no ceremony fallback",
                             qualification=qualification)
    return qualification


__all__ = ["TRUSTED_OPERATOR_CEREMONY", "VERIFIED_WORKPLANE_AUTHORITY",
           "EXTERNAL_ATTESTATION", "UNVERIFIED_CEREMONY", "EXTERNALLY_ATTESTED",
           "QUALIFIED_VERIFIED", "QUALIFIED_ATTESTED", "QUALIFIED_UNVERIFIED",
           "QUALIFIED_INVALID", "HEALTHY", "REVERTED", "SUPERSEDED", "MISSING",
           "AMBIGUOUS", "MODES", "EVIDENCE_STATUSES", "CAPABILITY_STATUSES",
           "approval_digest", "build_receipt", "derive_qualification",
           "production_trust_qualified", "validate_receipt"]