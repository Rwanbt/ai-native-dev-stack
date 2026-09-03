# ADR-0007: Transition Evidence, Atomic Policy Rotation, and What an Approval Approves

**Date:** 2026-09-03
**Status:** Accepted for the authority hardening on `spec`

## Context

The seventh external review of `386b326` was the first to report **P0 = 0**
inside the declared threat model. It left three findings, all reproduced first:

- ADR-0006 asserted that a policy change rotates the root in the same mutation.
  The controller did not enforce it. A policy-only mutation committed cleanly,
  producing a revision where the current policy and the current root disagree —
  a state the evaluator can never treat as authority. The sole normative writer
  was writing states it already knew were impossible;
- `_valid_root_chain` received one `facts` object — an observation of the
  *current* authority — and used it for every historical transition. It
  therefore asked "does today's authority satisfy the historical predicate"
  instead of "did this transition have the property when it was authorized";
- a `mutation_approval` named the state being reached and not the state being
  left. Reproduced: revision 1 approves a weak registry, revision 3 commits a
  stricter one, and replaying the revision-1 approval reaches revision 4 with
  the weak registry back.

## Decisions

### 1. A root carries the commitment of the policy it is written with

One rule, checked by the controller before any revision is written:

```text
approval_root.policy_digest == policy_commitment(candidate project_policy)
```

The atomicity ADR-0006 promised falls out of composition rather than needing a
second check: carrying a new policy commitment changes the root's own
commitment, and a changed root commitment already requires a predecessor and a
transition approval (ADR-0005 §5). A first draft of this fix had a separate
"a policy change must rotate the root" branch; it was **unreachable**, and
removing it is the honest result.

*Consequence:* policy authoring is heavier than artifact authoring. That is the
cost of a root of trust naming the policy it was established under, and it is
where a reviewer should push back if they think the coupling is wrong.

### 2. A transition is judged by the evidence bound to it

Rejected: putting the evidence inside the root artifact. The root is written by
the caller, and evidence about a transition is not the caller's statement about
itself — and the self-reference is circular, because the successor commitment
covers the transition approval.

The **manifest** records it, in the `root_chain` entry for the rotation:

```json
{"revision": 2, "digest": "...", "authority": {"commit": "<sha>", "approval_path": "<repo-relative>", "approval_digest": "<sha256>"}}
```

The controller populates it from what it actually observed when it authorized
the mutation: the commit that recorded the approval, where that approval lives,
and its content digest. The manifest is the commit marker, so an entry exists
exactly when the revision was committed.

*Amended after the eighth review.* The first version recorded the digest and
never read it back, so the binding was to a commit rather than to the approval
that commit was supposed to contain — a signature says something was signed,
not what. `evaluate_work` now reads the object out of the commit itself
(`git show <commit>:<path>`), canonicalizes it, and requires the digest to
match before deriving any facts. The working tree is deliberately not
consulted: what is on disk today proves nothing about what was approved then.

`_valid_root_chain` takes a `transition_facts` mapping keyed by successor UID,
and **a transition absent from it is invalid** — whether because the commit is
gone, the path is not in it, the object does not parse, or the digest does not
match. No bound evidence is not a pass.

*Limitation, stated:* the re-established facts are what Git can say about that
commit *now* — that it exists, and whether its signature verifies against the
signers the anchor pins today. A signer removed from the anchor since would
invalidate an old transition. That is fail-closed and, for a local threat
model, the honest reading: the project no longer trusts that identity.

### 3. An approval authorizes one transition, not one destination

`mutation_approval` binds `base_digest` as well as `target_digest`. An approval
is for `A → X`, not for "arriving at X".

The replay this closes is not theoretical, and the first version of the case
missed it: an intermediate revision that returns to *exactly* the earlier state
makes a replay legitimate, because the state is identical and the approved
transition genuinely applies. The case had to be rebuilt with a distinct third
state before it demonstrated anything.

**Decision on the review's P2, stated rather than left ambiguous:**

- `mutation_approval` is **transition-scoped** (option B). It names the state
  left and the state reached;
- `work_creation_approval` is **content-addressed** (option A). Genesis has no
  base to name, and two works with byte-identical contracts are the same
  contract at the same bar. The same admission may therefore create more than
  one work with that contract. If a project ever needs one-shot admission, the
  binding to add is a pre-created work identity, and this is the decision to
  revisit.

## Consequences

Asserted by A107 (five cases: the marker records commit, path and digest; a
digest naming another object, a path the commit does not hold, and a commit
predating the approval each invalidate the chain; a matching triple stays
valid), A104 (four cases: policy-only, a root committing to the policy
being left, a root committing to an unrelated policy, and the control where
policy and root move together), A105 (three: the commit marker records what
authorized each transition; current authority cannot supply historical facts
and an unbound transition is invalid; a committed rotation still converges) and
A106 (two: an old approval cannot undo a later strengthening, and an approval
issued against the current state is accepted).

Removing the three fixes makes five blocking cases fail while the four controls
keep passing.

What this does **not** change: genesis remains a trusted ceremony (ADR-0006),
`git_reviewed` and `ci_verified` still have no provider, and reusable attested
evidence is still not built.
