# ADR-0006: The Bootstrap Trust Boundary, and Policy Evolution

**Date:** 2026-09-03
**Status:** Accepted for the authority hardening on `spec`

## Context

A sixth external review of `92875e5` accepted the round-5 corrections and
found that the remaining P0 sits at a different layer: **who authorizes the
first project trust anchor?**

Round 5 noticed that putting `authorized_signers` inside a mutable anchor is
circular, and cut the circle by requiring the anchor to have exactly one commit
in its history. That is real, and it is not enough. On an uninitialized
repository a controlled actor can:

```text
generate a signing key  →  configure Git to verify it
                        →  bootstrap with its own fingerprint as authorized
                        →  sign the anchor commit
                        →  sign a creation approval
                        →  create an easy contract
                        →  CONVERGED
```

Every check passes truthfully. The anchor has one commit; the signature is
valid; the signer is authorized. All three statements descend from the same
actor. Reproduced: the test fixture *is* this protocol.

The review also found two structural P1s, both reproduced:

- the chain walk required **every** root — including historical predecessors —
  to carry the *current* policy commitment, so a project that legitimately
  evolved its policy could never validate its own genesis. ADR-0004 said the
  anchor deliberately does not pin the policy because policy evolves; the
  implementation made that unreachable;
- `WorkController` loaded the anchor without establishing that it was still
  valid, so the sole normative writer could accept a mutation under an anchor
  the evaluator would reject a moment later.

## Decisions

### 1. Genesis is a trusted ceremony, and that is stated rather than hidden

**Option A of the review, taken deliberately.** A root of trust cannot prove
its own legitimacy from data whose authority comes from that root. Adding
another field inside `project_trust.json` — `bootstrap_authorized_by`,
`owner`, a bootstrap signature — only moves the circle.

So the boundary is declared:

```text
Verified Work Plane guarantees begin AFTER a trusted operator has
established the project trust anchor. Establishing it is a privileged
operation inside the trusted computing base, and its legitimacy is an
assumption the runtime cannot verify.
```

Concretely:

- an uninitialized project is one where **no work can produce an authoritative
  `CONVERGED`** — that is already true (`PROJECT_TRUST_UNINITIALIZED`);
- `ainative trust bootstrap` remains in the CLI and is documented as a
  privileged trust-establishment operation, not one the Work Plane can prove
  the legitimacy of. Its output labels itself
  `"authority": "privileged_trust_establishment"`;
- **a deployment requirement**: trusted bootstrap must precede controlled-agent
  access. A controlled agent must not be given authority to perform the
  ceremony.

Claims are corrected to match. "Under `signature` an actor without the key
cannot produce a valid anchor" is true only *after* a trusted anchor exists;
before that, the actor makes the key.

Rejected: **Option B**, an external machine-verifiable root — OS-level trusted
configuration, pre-installed machine policy, an externally signed bootstrap
artifact, remote attestation. It is the only thing that would actually protect
genesis against a controlled actor, and it needs a trust source this product
does not have and should not invent. If the threat model ever includes an
adversary present *before* bootstrap, that is the work; it is not this.

*What the runtime still cannot distinguish, said plainly:* a trusted human
creating the first anchor, from an agent creating it. `initialized_by` is a
string the caller supplied. It is metadata, and nothing verifies it.

### 2. A transition is judged under the policy that authorized it

The chain walk now resolves each root's policy from a **committed policy
chain**, recorded in the manifest exactly as the root chain is, and:

- only the **current** root must carry the current policy commitment;
- every earlier root must carry a commitment the project actually committed;
- a transition into root *R* is judged under **R's predecessor's** policy — its
  approval predicate and its required facts.

Judging history by today's rules would let a later, weaker policy retroactively
authorize a transition it never saw. The invariant is `P0` authorized `P1` and
`P1` authorized `P2`, not "the newest policy authorizes everything".

*Consequence, stated:* changing the policy requires rotating the root in the
same mutation, because the current root must carry the current policy
commitment. That is not a workaround — the root of trust names the policy it
was established under, so a policy change *is* a new root generation, and the
transition approval issued under the predecessor's policy is precisely the
authorization for it. Rotation is fully governed since ADR-0005.

*Limitation, stated:* the facts a historical transition is measured against are
observed **now**, not then. A local checkout has no record of what was
observable at the time. The predicate and the required facts come from the
historical policy; the observation does not.

### 3. One anchor verification, used by the writer and the judge

`bootstrap.verified_anchor()` locates, loads and verifies. `WorkController`
and `evaluate_work` both call it, so they cannot drift apart. An anchor that no
longer establishes anything refuses a write (`UNGOVERNED_PROJECT`) rather than
producing a revision the evaluator will then decline to judge.

Fail-closed at evaluation was already true and prevented a false `CONVERGED`.
Fail-closed at the sole normative writer is what a sole normative writer is
for.

## Consequences

Asserted by A101 (two cases: the self-bootstrapped project converges — the
boundary — and the runtime makes no claim about who performed genesis), A102
(three: an authorized policy change converges, a later weaker policy does not
authorize an old transition, and a policy never committed authorizes nothing)
and A103 (three: an invalid anchor authorizes neither a mutation nor a new
work, and a valid one still does).

A101 asserts a limitation rather than a defence. If an external trust source is
ever added, **it must fail** and be rewritten — that is its purpose.

Removing the two P1 fixes makes four blocking cases fail while the controls
keep passing.
