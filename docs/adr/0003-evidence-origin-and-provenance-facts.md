# ADR-0003: Evidence Origin, Provenance Facts, and the Mutation Bar

**Date:** 2026-09-03
**Status:** Accepted for the authority hardening on `spec`

## Context

An external review of `13d2550` found four ways a controlled actor could still
manufacture `CONVERGED`, all reproduced before any code was changed:

- a complete, schema-valid `verification_run` written by hand converged, and
  masked a verification that genuinely failed;
- a clean source checkout capped the provenance of evidence, roots and
  approvals alike, so a work directory elsewhere inherited its cleanliness;
- provenance was a numeric ladder, so a signature satisfied a policy demanding
  CI;
- rewriting the command a verification runs turned a failing check into
  `CONVERGED`, because freshness only proves evidence matches the *current*
  rules, however those rules got there.

Each fix admitted more than one answer. This records which was taken.

## Decisions

### 1. Evidence is produced by the evaluator, not authenticated

Options were: authenticate recorded runs, keep a tamper-evident store, or
re-execute. Against a local actor with write access to the work directory there
is no signature that actor could not also produce and no store they could not
reach, so authentication cannot work at this boundary.

`evaluate_work` therefore executes the declared verifications itself and judges
only what it just produced. Recorded runs are a local execution log, not an
audit trail — nothing authenticates them — and they are never an input.

*Cost, stated:* convergence now runs the verifications. A verdict is no longer
cheap, and reusable evidence is not a local concept.

*Consequence, stated:* per-evidence freshness stops being a staleness gate on
the in-process path — the evidence is always current for a still checkout. What
it still catches is a checkout moving underneath a running verification, which
is a race. A57 tests that and nothing more.

*Where this changes:* independently attested evidence — a signed CI attestation
this build cannot yet verify — is the case for reusing evidence rather than
re-running it. That is the extension point, not a gap to fill locally.

*Two modes, named so the second is not forgotten.* The plan introduced
`STALE_SCOPE`, `STALE_DEPENDENCY` and `STALE_REPO` precisely so an unrelated
edit would not force a full rerun. Re-execution gives that up:

- **Local secure mode** (what this build does): every convergence re-executes
  every declared verification. Nothing local is reusable, so nothing stale can
  be selected. Correct, and prohibitive for a large suite — a monorepo E2E run,
  an Android build, browser tests.
- **Attested mode** (designed for, not built): evidence carrying an
  independently verified CI or signature attestation is reusable, and the
  freshness states select it. The freshness engine is kept complete for this
  reason, not because the local mode needs all of it.

Claiming the original selective-rerun objective is delivered requires the
second mode. It is not delivered.

### 2. Provenance is independent facts, not a ranking

`git_recorded`, `git_reviewed`, `ci_verified`, `signature_verified` are separate
booleans. A policy names the ones it needs. No fact substitutes for another:
a signature is not a review and not a CI run (A77-A79).

`git_reviewed` and `ci_verified` are not observable from a checkout at all, so a
policy requiring either cannot be satisfied by this build. That is fail-closed
and it is a real functional limit.

### 3. Provenance is observed per object, in two domains

The checkout is observed for the code under verification; the normative
artifacts are observed at their own location for authority. A work directory
outside a repository establishes nothing, whatever the repository it describes.

The run log is deliberately excluded from the authority observation: a fresh
log entry must not make the rules look tampered with.

### 3b. A mutation approval is an artifact, not an argument

Checking an approval's content against the policy while measuring the
*previous state's* provenance proves the previous state was clean, not that
anyone approved anything. An actor able to call the API could build the exact
record that authorized its own weakened state — the third review found this,
and the first version of the test helper demonstrated it.

`mutate` therefore takes a path, and the controller observes that artifact.
Under `git_recorded` the approval must already be recorded before the mutation
it authorizes; under `signature_verified` an actor without the key cannot
produce one at all. That last case is where the bar stops being a formality.

### 4. Every normative artifact is behind the mutation bar

The alternative was to gate only the trust base — registry, policy, root,
specifications — and leave requirements, acceptance criteria and tasks free.
Rejected: a requirement is a success condition, and narrowing one removes an
obligation exactly as changing a command does.

So any change to any normative artifact needs a `mutation_approval` that the
policy of revision N authorizes for exactly revision N+1. A candidate policy
never authorizes its own adoption. `create()` is exempt: genesis has no previous
authority to ask.

*Cost, stated:* ordinary authoring now needs approvals. A project that wants
that cheap sets `required_mutation_facts` to `{}` — the approval is still
explicit and still names the exact next state.

### 5. An empty fact requirement is allowed; the key is not

`required_mutation_facts: {}` is a deliberate local posture. Omitting the key
is a schema error, so nothing requires nothing by accident.

### 6. A transition approval binds the successor's content

Binding the UID alone approves a name. `successor_commitment` digests the
candidate's content excluding its own self-referential fields (A86).

## Consequences

Each decision is asserted by a named case: A72-A73 (origin), A74-A79
(provenance), A80-A83 (mutation bar), A84-A85 (approval provenance), A86
(successor content), A87-A88 (work and revision binding), A89-A90 (registry),
A91-A92 (approval origin), A93 (authority stability).

None of this closes the finding by itself. The standard for an authority
correction is external review, and this ADR exists so a reviewer can disagree
with a decision rather than reverse-engineer it.
