# ADR-0005: Admitting the Initial Contract, and Authorizing the Signer

**Date:** 2026-09-03
**Status:** Accepted for the authority hardening on `spec`

## Context

A fifth external review of `2f0420b` accepted the round-4 corrections and found
two more P0s and two structural P1s. All four were reproduced first.

- ADR-0004 stopped a new work from inventing its own approval root, and stopped
  there. `WorkController.create()` still accepted the complete initial
  normative state from its caller. A controlled actor could create a sibling
  work under the project's legitimate pinned root, choose a trivial
  requirement, a trivial acceptance criterion and an easy verification, and
  converge. Root and policy both legitimate; nobody authoritative had agreed
  what *this* work must accomplish.
- `signature` proved that Git accepted a signature. It did not ask whose. A
  repository may accept several signing identities, and an actor allowed to
  sign ordinary commits is not thereby allowed to approve a policy change. The
  signer identity was never compared with anything.
- `git log -1 --format=%G? -- a b` reports the most recent commit touching
  *either* path. One signed commit therefore made a whole path set look signed
  while another path's content came from an unsigned one.
- The manifest recorded which roots were committed, but the chain walk still
  terminated at any predecessor-less root. A root could change content, declare
  no predecessor, and be read as a second genesis — making
  `transition_approval` optional exactly where it decides something.

## Decisions

### 1. Creating a work contract proposes; admission promotes

The mutation bar covers every normative artifact because requirements and
acceptance criteria are success conditions: narrowing one removes an
obligation. Revision 1 states the whole of what must be accomplished, so the
same property applies to it, and "genesis has no previous authority to ask" was
never true once the *project* had authority.

A work is admitted by a `work_creation_approval` at the fixed path
`<work>/creation_approval.json`, binding:

```text
trust_uid + trust_digest     the exact project anchor
genesis_digest               the exact initial normative digest
predicate_id                 the anchor's own predicate
```

*Fixed path, not a parameter.* The evaluator has to find it too, and an
authority artifact whose location the caller chooses is one the caller can
decline to mention.

*The anchor's predicate, not a new one.* Whoever pinned the project is who may
admit a work into it. A separate creation predicate would be a second dial with
no separate meaning.

*No `work_uid`.* At creation the controller generates it, so an approval could
not name it in advance. The approval binds the contract's content instead — two
works with byte-identical contracts are the same contract, and a different
contract needs a different approval.

*Checked twice, deliberately.* The controller refuses to write an unadmitted
work; the evaluator refuses to converge on one. An actor that writes a work
directory by hand bypasses the first and not the second. The evaluator
recomputes the genesis digest from `revisions/1/` rather than reading a field,
because a field would be a claim by whoever last wrote the manifest.

### 2. A signature predicate needs validity *and* authorization

These are separate questions and only the first is Git's:

```text
cryptographic validity   Git: %G? == G against the configured keyring
authorization            the signer identity is one this project pinned
```

The project trust anchor gains `authorized_signers`, a list of key
fingerprints (`%GF`, falling back to `%GK`) — the same field for GPG and SSH
signing. `signature_verified` is true only when every observed path's
last-writing commit verifies *and* its signer is in that list.

`authorized_signers=None` establishes nothing. Where no set is pinned there is
nobody to have authorized anything, and the answer is `False` rather than "any
valid signature".

Rejected: trusting `gpg.ssh.allowedSignersFile` or `.git/config` as the source
of authority. Both are in the repository, and an actor with commit rights can
add a key to either. They decide what Git will *verify*; the anchor decides
what this project will *accept*.

### 3. The anchor is written exactly once

Pinning the signers in the anchor is circular on its own: an actor that
rewrites the anchor to add its key is then measured against the list it just
wrote. That is not a hypothetical — it was the first thing the A98 case caught
in this round's own fix.

So the anchor must also have exactly one commit in its history. A file with a
single commit still says what its author said, and the circle is cut.

*Cost, stated:* changing a governed project's authorized signers is not an
edit. It is a new project trust anchor — an explicit, out-of-band decision.
That is what a root of trust should cost, and it is the structural form of the
invariant ADR-0004 only asserted through an API refusal: **a governed project
never re-bootstraps silently.**

### 4. Provenance over a set of objects is conjunctive

`signature_signers()` resolves the signing identity **per path**, one
`git log -1` per path, and a path whose last commit is unsigned contributes
`None`. A caller requiring a signature over a set finds no `None` — never one
signed commit standing in for the rest.

*Cost, stated:* one subprocess per observed path. The path sets here are the
declared execution scope plus covered paths, and the authority artifact list;
a single walk of `git log --name-only` would be one call but has to parse
Git's path quoting to stay correct, and correctness came first.

### 5. A chain terminates at the pinned genesis, not at any root

Two enforcement points, because they refuse different things:

- the **controller** refuses to write a root whose commitment changed unless it
  names the committed root it replaces as its predecessor and carries a
  transition approval. That is structural — was the transition even claimed;
- **`_valid_root_chain`** treats a predecessor-less root as terminal only when
  its commitment equals the anchor's pinned genesis. That is authority — is
  this the chain the project started.

`genesis_digest=None` keeps the older behaviour for callers with no project
anchor. The production path always supplies it, and a work with no anchor is
already `PROJECT_TRUST_UNINITIALIZED`.

## Consequences

Asserted by A97 (five cases: unadmitted, self-admitted, admission removed after
the fact, admission for another contract, and the admitted control), A98 (four:
unauthorized signer, authorized control, widened verifier configuration,
rewritten anchor), A99 (three: mixed set, fully signed control, no pinned set)
and A100 (four: no predecessor, wrong predecessor, predecessor-less root at
evaluation, proper rotation control).

Each was reproduced against `2f0420b` first. Removing the four fixes makes
eleven blocking cases fail while the controls keep passing.

What this does **not** close: under `recorded_owner_ack`, at any level, an
actor with commit rights remains the whole bar. `git_reviewed` and
`ci_verified` still have no provider. And a project that loses its signing key
cannot rotate signers without establishing a new anchor — deliberate, and a
real operational cost.
