# ADR-0002: Interpretations Chosen Where the Hardening Plan Under-Specifies

**Date:** 2026-09-03
**Status:** Accepted for the H0–H13 implementation on `spec`

## Context

The production hardening plan states several requirements as prose that does
not determine a rule. "Scope matches", "must cover relevant implementation
paths", "eligible gaps", and "`NOT_CONVERGED` or `INVALID`" each admit more
than one faithful implementation.

Those choices were made during implementation and were, until this record,
only visible by reading the code. An engine whose blocking verdict depends on
an unwritten reading is not reviewable, and a later change could silently
reinterpret one of them. This ADR names each choice so it can be argued with.

## Decisions

### 1. A waiver matches a gap by target UID and gap code

Plan section 25 requires "target valid" and "scope matches". A waiver
suppresses a gap when `waiver.target.uid == gap.uid` **and**
`waiver.scope == gap.code`. Both, not either.

*Rejected:* matching by target alone, which would let one waiver silently
absorb every future gap that lands on the same artifact.

### 2. A waiver may never suppress a gap that says authority is unknown

"Eligible gaps" is defined by exclusion. `UNWAIVABLE` holds
`FRESHNESS_UNAVAILABLE`, `ROOT_OF_TRUST_INVALID`,
`POLICY_COMMITMENT_INVALID`, `INVALID_VERIFICATION_EVIDENCE` and
`UNRELATED_VERIFICATION_EVIDENCE`. A waiver may excuse unfinished work; it may
never excuse the engine's inability to establish who authorized anything.

*Rejected:* letting a sufficiently privileged waiver suppress anything, which
would make the fail-closed rule of section 1.4 waivable by whoever holds the
waiver predicate.

### 3. `INVALID` means the inputs could not be evaluated

Section 24 permits "`NOT_CONVERGED` or `INVALID`" without saying which.
`INVALID` is returned when any gap is in `UNEVALUABLE` — no freshness
evaluation, no or invalid root of trust, an invalid policy commitment, a run
that is not validated evidence, or an unauthorized or malformed waiver or
human approval. Everything else that blocks is `NOT_CONVERGED`.

The distinction carries information the caller needs: "the work is not
finished" and "I could not determine who is allowed to say so" call for
different responses. Neither is a success, so the fail-closed property is
unchanged either way.

### 4. `direct_scope` coverage is checked against the tasks behind the requirement

"Must cover relevant implementation paths" is read as: for the requirement a
specification verifies, every `implementation_paths` entry of every task
attached to that requirement must match one of the specification's
`covered_implementation_paths` patterns. A pattern matches by exact equality,
by `fnmatch`, or as a `prefix/**` subtree.

*Rejected:* requiring the specification's `execution_scope` to contain
implementation files, which section 11 forbids explicitly — a black-box test
runs `tests/**` and covers `src/**`.

### 5. `STALE_REPO` is head drift with no scope or dependency drift

The repository moved but nothing the evidence depended on changed. It is
emitted and deliberately excluded from `BLOCKING_FRESHNESS`, matching the
policy's own "warning or information" wording. An unrelated commit therefore
never invalidates a run.

### 6. The substance contract lives on the command, not on the specification

`verification_specification.substance_requirement` is a string in the frozen
schema and cannot carry `{type, minimum_observations}`. The contract is
declared on the command registry entry, which is already part of the trust
base, is digest-bound into every run, and is where the runner can validate it
at load time.

*Rejected:* widening the specification schema, which would have been a
breaking change to a frozen contract for something the registry already binds.

### 7. Waivers and approvals are held to the success-condition provenance bar

A waiver or a human approval changes what counts as success, so it is measured
against `policy.success_condition_mutation_provenance`, not
`verification_evidence_provenance`. A project may demand stronger authority to
excuse a gap than to record a test result.

### 8. `snapshot_head` was added as required at `schema_version` 1

Binding the checkout head is part of "exact Repository Snapshot" in section
1.3. Adding it as required without a version bump is a breaking change in
principle; in fact no artifact of this schema exists outside this branch's own
tests, so there is nothing to migrate. The moment a `verification_run` is
persisted outside this repository, this stops being true and the next such
change needs a version.

## Consequences

Each decision is asserted by a named test, so changing one breaks a test
rather than quietly changing a verdict:

- 1, 2 and 7 — `tests/test_workplane_authorization.py`
- 3 — `test_verdicts_separate_unevaluable_inputs_from_unfinished_work`
- 4 — `test_relationship_decides_what_coverage_a_specification_must_declare`
- 5 — `test_unrelated_commit_is_information_while_a_changed_specification_blocks`
- 6 — `tests/test_workplane_substance.py`
- 8 — every binding fixture, which now fails without the field

These are readings, not derivations. A reviewer who disagrees with one is
disagreeing with a decision recorded here, which is the point.
