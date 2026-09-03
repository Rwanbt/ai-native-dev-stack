# ADR-0004: Project Trust Bootstrap, and Predicates as Mechanisms

**Date:** 2026-09-03
**Status:** Accepted for the authority hardening on `spec`

## Context

A fourth external review of `2a6f838` accepted the round-3 corrections and
found two more P0s, both reproduced before anything was changed:

- a controlled actor prepared a weakened command registry, built the exact
  `mutation_approval` its own next state needed, committed it, and the
  controller accepted it — because the policy's predicate was *named* `review`
  while requiring only `git_recorded`. The verdict moved `NOT_CONVERGED` →
  `CONVERGED` on a verification that genuinely failed;
- a work created by `WorkController.create()` established its own policy,
  approval root, command registry and verification rules, and converged. No
  project-level authority existed to contradict it, so every N → N+1
  protection could be bypassed by making a new N.

Both are the same shape: something that looked like authority was actually a
statement by the party it was supposed to constrain.

## Decisions

### 1. A predicate is a mechanism, not an identifier

`predicate_id` was compared as a string. The engine then measured the approval
against `required_mutation_facts`, which the same policy also chose. A policy
could therefore name `review` and require a commit.

`predicates.py` now holds a closed table mapping each predicate to the facts
that satisfy it:

| predicate | requires | an actor with commit rights can satisfy it |
| --- | --- | --- |
| `signature` | `signature_verified` | no |
| `git_review` | `git_reviewed` | no |
| `ci_attestation` | `ci_verified` | no |
| `recorded_owner_ack` | `git_recorded` | **yes** |

The requirement is the mechanism's, not the policy's; `required_mutation_facts`
may add to it and never subtract. A predicate this build does not implement is
never satisfied, so a project cannot acquire authority by naming one.

`recorded_owner_ack` is kept because a single maintainer is a real posture.
It is named for what it is, and the alternative — deleting it — would push the
same projects onto `{}`, which is weaker and less legible.

*Cost, stated:* there is no longer a posture where an approval need not even be
recorded. `required_mutation_facts: {}` still parses, but the weakest predicate
imposes `git_recorded` regardless. An approval nobody recorded is an argument,
and round 3 closed that door.

### 2. The signature predicate is implemented, and it is the documented default

Rejected: shipping four predicate names and implementing none, which is how
`git_reviewed` came to be documented as the portable default while `observe()`
could never establish it. A predicate nothing satisfies reads as strong and
fails closed at the worst moment.

`provenance.signature_verified()` asks Git whether the commit that last wrote
the observed paths carries a signature that verifies — `git log -1 --format=%G?`
returning `G`. Git decides, against the configured keyring or allowed-signers
file. An actor without the key cannot make it say `G`, which is the whole
distinction the mutation bar rests on.

Two consequences worth stating:

- the object observed is the commit that last touched *these paths*, not
  `HEAD`. A signed head commit says nothing about a file someone else committed
  ten commits earlier, and a policy asking for a signature on an approval is
  asking about the approval;
- `git_reviewed` and `ci_verified` remain unimplementable here. They are kept
  as facts because they are real and independent, and a policy requiring either
  fails closed. **The supported production default is `signature`.**

### 3. Project trust is bootstrapped before any work exists

`create()` had no previous authority to ask, which is true at genesis and was
taken to mean genesis needed no authority at all.

The state machine is now explicit:

```text
UNINITIALIZED  --explicit bootstrap-->  GOVERNED  --> work creation
```

The anchor is `.ai-native/trust/project_trust.json`, in the repository rather
than in any work directory, because what it has to outlive is the work
directory. It pins the approval root the project starts from and declares the
predicate the anchor itself must satisfy — measured by observing the file, the
way every other authority artifact is.

- A work created in a governed project whose approval root the anchor does not
  pin is refused: `UNGOVERNED_GENESIS`.
- A work no anchor pins is not refused at creation — creating a directory is a
  local act — but it is unevaluable: `PROJECT_TRUST_UNINITIALIZED`, which is
  `INVALID`, never `CONVERGED`.
- `bootstrap()` refuses to replace an existing anchor. Rotating the root of a
  governed project is a root transition, which the trust chain already governs.
  It is not a second genesis.

Under `signature` an actor without the key cannot produce a valid anchor at
all. Under `recorded_owner_ack` it can, and that is the named weak posture
again — the same distinction, applied one level up.

*What the anchor deliberately does not pin.* The policy. Every change to it
since bootstrap passed the mutation bar, which checks each step against the
authority in force at the time — a stricter statement than a frozen digest, and
one that does not make ordinary policy authoring require a re-bootstrap. The
anchor records `policy_digest` as what was in force at genesis; that is what it
is, a record.

*What the anchor pins instead.* The **genesis** root, matched against the
work's committed root chain rather than its current root. Pinning the current
root would make rotation impossible without a second genesis, which is the
thing this ADR exists to prevent.

### 4. The committed root chain lives in the manifest

`root_history()` listed `revisions/` and read every `approval_root.json` it
found. Crash consistency deliberately permits a promoted revision whose
manifest replace never happened, so that read authority out of a write that did
not occur.

The manifest — which *is* the commit marker — now carries `root_chain`, one
entry per rotation, recording the revision and the root's commitment. A
revision only enters it through the atomic replace that makes a revision
committed at all, and each root is re-digested when read, so a historical file
cannot be exchanged afterwards.

Rejected: an append-only side file. It would need the same atomicity as the
manifest to be trustworthy, which makes it the manifest with extra steps.

## Consequences

Asserted by A94 (self-recorded approval, with the satisfied-predicate control),
A95 (genesis: uninitialized, foreign root, permitted sibling work, refused
re-bootstrap, unsigned anchor, unreadable anchor) and A96 (orphan revision,
committed rotation, swapped historical root).

Each was reproduced against `2a6f838` first, and each fails when its fix is
removed — checked by reverting the three fixes and re-running the file.

What this does **not** close: under `recorded_owner_ack`, at either level, an
actor with commit rights is still the whole bar. That posture is now named
rather than disguised, which is the correction; it is not protection.
