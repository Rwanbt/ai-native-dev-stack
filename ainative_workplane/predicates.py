"""What a named approval predicate actually requires before it is satisfied.

An approval carries a `predicate_id`. Until now the engine checked that the
string matched the one the policy configured and then measured the approval
artifact against `required_mutation_facts`. A policy could therefore configure
a predicate named `"review"` while requiring only `git_recorded`, and an actor
with commit rights would satisfy it by writing the approval and committing it.
The label said review; the machine asked for a commit. The fourth review
called this what it is: `predicate_id` was an identifier, not a predicate.

So a predicate is a named mechanism, and the mechanism states what has to be
established about the approving artifact. The set is closed and every member
maps to a fact the runtime can actually observe: a predicate nothing can
satisfy is worse than no predicate, because it reads as strong.

One member is deliberately weak. `recorded_owner_ack` requires only that the
approval was committed, which an actor with commit rights can do for itself.
It is kept because a single-maintainer project is a real posture -- and it is
named so that nobody reads it as review.
"""

from __future__ import annotations

from typing import Any, Mapping

from .provenance import OBSERVABLE_FACTS


# The closed set. A predicate is satisfied when the facts named here are
# established about the artifact claiming it, not when its name sounds right.
PREDICATE_REQUIREMENTS: dict[str, dict[str, bool]] = {
    "signature": {"signature_verified": True},
    "git_review": {"git_reviewed": True},
    "ci_attestation": {"ci_verified": True},
    "recorded_owner_ack": {"git_recorded": True},
}

# Predicates an actor with write and commit access cannot satisfy alone. The
# distinction is the whole point of the mutation bar, so it is stated here
# rather than left for a reader to infer from the table above.
INDEPENDENT_PREDICATES = frozenset({"signature", "git_review", "ci_attestation"})

# Kept honest by construction: a predicate may not require a fact nothing can
# establish, and the table may not drift away from the observable set.
assert all(fact in OBSERVABLE_FACTS for requirement in PREDICATE_REQUIREMENTS.values() for fact in requirement)


def predicate_requirements(predicate_id: str) -> dict[str, bool] | None:
    """Return what the named predicate demands, or None when it names nothing."""

    return PREDICATE_REQUIREMENTS.get(predicate_id)


def predicate_refusal(predicate_id: Any, facts: Any) -> str | None:
    """Return why the predicate is not satisfied by these facts, or None.

    @contract An unknown predicate is never satisfied. A policy that names a
    mechanism this build does not implement fails closed, so a project cannot
    acquire authority from a word.
    """

    if not isinstance(predicate_id, str):
        return "the approval names no predicate"
    required = PREDICATE_REQUIREMENTS.get(predicate_id)
    if required is None:
        return f"predicate {predicate_id!r} is not a mechanism this build implements"
    missing = tuple(sorted(required)) if facts is None else facts.unmet(required)
    if missing:
        return f"predicate {predicate_id!r} requires {', '.join(missing)}, which is not established"
    return None


def independent(predicate_id: Any) -> bool:
    """Whether satisfying this predicate needs someone other than the actor."""

    return predicate_id in INDEPENDENT_PREDICATES


def describe(required: Mapping[str, Any]) -> str:
    return ", ".join(name for name, needed in sorted(required.items()) if needed) or "nothing"


__all__ = ["PREDICATE_REQUIREMENTS", "INDEPENDENT_PREDICATES", "predicate_requirements", "predicate_refusal", "independent", "describe"]
