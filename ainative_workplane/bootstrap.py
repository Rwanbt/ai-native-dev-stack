"""The project trust anchor: what a work contract is created *under*.

Until the fourth review, `WorkController.create()` was the whole of genesis.
Creating a work directory established its policy, its approval root, its
command registry and its verification rules in one act, and the exemption that
made that possible -- genesis has no previous authority to ask -- meant an
actor could simply create another work with rules it preferred. Every N -> N+1
protection held, and was irrelevant, because nothing made N itself answerable.

So project trust is separated from work creation:

    UNINITIALIZED  --explicit bootstrap-->  GOVERNED  --> work creation

The anchor is a file in the repository, not in the work directory, because the
thing it has to outlive is the work directory. It pins the approval root and
the policy the project is governed under, and it names the predicate that must
hold for the anchor itself. Under `signature` an actor without the key cannot
produce a valid one; under `recorded_owner_ack` it can, which is a real posture
for a single maintainer and is named so nobody mistakes it for review.

A work created in a governed project must reference the pinned root. A work
created where no anchor exists is not refused -- it is simply not governed, and
the evaluator says so rather than converging on rules its subject chose.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import ContractError, canonical_digest, generate_uid, validate_artifact
from .predicates import predicate_refusal, predicate_requirements
from .provenance import UNOBSERVED, commit_count, observe_artifact, observe_artifacts
from .trust import approval_root_commitment, policy_commitment

# Repository-relative, and deliberately beside the work directories rather
# than inside any one of them.
TRUST_RELATIVE = Path(".ai-native") / "trust" / "project_trust.json"


class BootstrapError(RuntimeError):
    """The project trust anchor could not be established or read."""


def _without(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return {name: _without(item, key) for name, item in value.items() if name != key}
    if isinstance(value, list):
        return [_without(item, key) for item in value]
    return value


def trust_commitment(anchor: Mapping[str, Any]) -> str:
    """Digest the anchor's content without its own self-reference."""

    return canonical_digest(_without(anchor, "trust_digest"))


def locate(start: str | os.PathLike[str]) -> Path | None:
    """Find the anchor governing this location, searching upwards.

    Upwards because a work directory lives inside the project it belongs to,
    and the project is what holds the anchor.
    """

    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / TRUST_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def load(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read and validate an anchor, refusing anything malformed."""

    target = Path(path)
    try:
        anchor = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BootstrapError("PROJECT_TRUST_UNREADABLE") from error
    if not isinstance(anchor, Mapping) or anchor.get("schema_name") != "project_trust":
        raise BootstrapError("PROJECT_TRUST_UNREADABLE")
    try:
        validate_artifact(anchor)
    except ContractError as error:
        raise BootstrapError(f"PROJECT_TRUST_INVALID:{error.code}") from error
    if anchor["trust_digest"] != trust_commitment(anchor):
        raise BootstrapError("PROJECT_TRUST_INVALID:SELF_COMMITMENT")
    return dict(anchor)


def bootstrap(repository_root: str | os.PathLike[str], *, approval_root: Mapping[str, Any], policy: Mapping[str, Any], initialized_by: str, predicate_id: str = "signature", authorized_signers: Iterable[str] = ()) -> Path:
    """Pin what this project trusts. Refuses to replace an existing anchor.

    @contract A governed project never re-bootstraps silently. Rotating the
    root of a governed project is a root transition, which the trust chain
    already governs; it is not a second genesis.
    @contract `authorized_signers` is where the trusted verifier configuration
    stops being the actor's. Git decides whether a signature is valid against
    whatever keyring or allowed-signers file the repository configures, and an
    actor can add a key to that file. It cannot add itself here without
    rewriting the anchor -- which makes the anchor's own last commit unsigned
    by an authorized identity, and the anchor then establishes nothing.
    """

    root = Path(repository_root)
    target = root / TRUST_RELATIVE
    if target.exists():
        raise BootstrapError("PROJECT_TRUST_ALREADY_INITIALIZED")
    if predicate_requirements(predicate_id) is None:
        raise BootstrapError(f"PROJECT_TRUST_INVALID:UNKNOWN_PREDICATE:{predicate_id}")
    anchor: dict[str, Any] = {
        "schema_name": "project_trust",
        "schema_version": 1,
        "uid": generate_uid("trust"),
        "trust_digest": "0" * 64,
        "policy_digest": policy_commitment(policy),
        "approval_root": {"uid": approval_root["uid"], "digest": approval_root_commitment(approval_root)},
        "bootstrap_predicate": {"predicate_id": predicate_id, "policy_digest": policy_commitment(policy)},
        "authorized_signers": sorted(set(authorized_signers)),
        "bootstrap": {"initialized_at": datetime.now(timezone.utc).isoformat(), "initialized_by": initialized_by},
    }
    anchor["trust_digest"] = trust_commitment(anchor)
    validate_artifact(anchor)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(anchor, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return target


def governs(anchor: Mapping[str, Any], *, approval_root: Any, root_history: Iterable[Mapping[str, Any]] = ()) -> str | None:
    """Return why this work is not one the anchor governs, or None.

    The anchor pins the root the project started from, and the work's committed
    root chain must contain it. Anything after that is a root transition, which
    the trust chain already governs -- each successor carries an approval its
    predecessor's predicate had to satisfy. Pinning the *current* root instead
    would make rotation impossible without a second genesis, which is the thing
    this module exists to prevent.

    The policy is deliberately not pinned. Every change to it since bootstrap
    passed the mutation bar, which checks each step against the authority in
    force at the time -- a stricter statement than a frozen digest, and one
    that does not make ordinary policy authoring require a re-bootstrap. The
    anchor records `policy_digest` as what was in force at genesis, and that is
    what it is: a record.
    """

    if not isinstance(approval_root, Mapping):
        return "the work declares no approval root to compare with the project trust anchor"
    pinned = anchor["approval_root"]
    candidates = [*root_history, approval_root]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        if candidate.get("uid") == pinned["uid"] and approval_root_commitment(candidate) == pinned["digest"]:
            return None
    return "the project trust anchor pins a root this work never committed"


def anchor_refusal(path: str | os.PathLike[str], anchor: Mapping[str, Any]) -> str | None:
    """Return why the anchor itself carries no authority, or None.

    Two checks, and the second exists because the first alone is circular.

    The anchor is measured the way every other authority artifact is: by
    observing the object, against the identities *it* pins. But an actor that
    rewrites the anchor to add its own key would then be measured against the
    list it just wrote. So the anchor must also never have been rewritten: one
    commit in its history, the one that established it. A file with a single
    commit still says what its author said.

    *Cost, stated:* changing the authorized signers of a governed project is
    therefore not an edit. It is a new project trust anchor — an explicit,
    out-of-band decision, which is what a root of trust should cost.
    """

    target = Path(path)
    rewrites = commit_count(target.parent, target.name)
    if rewrites != 1:
        return (
            "the project trust anchor is not recorded exactly once"
            if rewrites >= 0 else
            "the project trust anchor's history could not be read"
        ) + f" ({rewrites} commits touch it); a governed project never re-bootstraps silently"
    return predicate_refusal(anchor["bootstrap_predicate"]["predicate_id"], observe_artifact(path, authorized_signers=anchor["authorized_signers"]))


CREATION_APPROVAL = "creation_approval.json"


def creation_approval_path(work_dir: str | os.PathLike[str]) -> Path:
    """Where a work records the approval that admitted its initial contract.

    A fixed name rather than a parameter: the evaluator has to find it too, and
    an authority artifact whose location the caller chooses is an authority
    artifact the caller can decline to mention.
    """

    return Path(work_dir) / CREATION_APPROVAL


def admits(anchor: Mapping[str, Any], *, approval: Any, genesis_digest: str, facts: Any) -> str | None:
    """Return why project authority did not admit this initial contract, or None.

    @contract The approval names the exact initial normative digest and the
    exact anchor, and satisfies the anchor's predicate as an observed artifact.
    Creating a work contract proposes what must be accomplished; this is what
    promotes the proposal to authority.
    """

    if approval is None:
        return "the initial work contract carries no creation approval"
    try:
        validate_artifact(approval)
    except ContractError as error:
        return f"the creation approval is not a valid artifact: {error.code}"
    if approval.get("schema_name") != "work_creation_approval":
        return "the creation approval is not a work creation approval"
    if approval.get("trust_uid") != anchor["uid"] or approval.get("trust_digest") != anchor["trust_digest"]:
        return "the creation approval was issued under a different project trust anchor"
    if approval.get("genesis_digest") != genesis_digest:
        return "the creation approval names a different initial contract than the one being written"
    predicate = anchor["bootstrap_predicate"]["predicate_id"]
    if approval.get("predicate_id") != predicate:
        return "the creation approval uses a predicate the project trust anchor does not configure"
    return predicate_refusal(predicate, facts)


def read_creation_approval(work_dir: str | os.PathLike[str], anchor: Mapping[str, Any]) -> tuple[Any, Any]:
    """Load a work's creation approval and observe the artifact it actually is."""

    path = creation_approval_path(work_dir)
    if not path.is_file():
        return None, UNOBSERVED
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, UNOBSERVED
    return record, observe_artifacts([path], authorized_signers=anchor["authorized_signers"])


__all__ = ["CREATION_APPROVAL", "TRUST_RELATIVE", "BootstrapError", "admits", "anchor_refusal", "bootstrap", "creation_approval_path", "governs", "load", "locate", "read_creation_approval", "trust_commitment"]
