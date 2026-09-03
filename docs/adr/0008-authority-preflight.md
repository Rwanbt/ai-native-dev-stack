# ADR-0008: Authority Is Decided Before Anything Executes

**Date:** 2026-09-03
**Status:** Accepted for the authority hardening on `spec`

## Context

The ninth external review found two P0s in `b96cb5b`, both reproduced first,
and both closed by one change.

**Commands ran before authority was proved.** The order in `evaluate_work` was:
load authority → observe it → *execute the declared verifications* → check
drift → assess evidence → add project-trust gaps → converge. So a work no
project trust anchor governed still ran its registry command; the refusal
arrived afterwards. Reproduced with a command that writes a sentinel file: the
verdict was `INVALID` **and the file existed**. The verdict was fail-closed;
the execution boundary was not.

**A human-only contract never walked the chain.** The complete root-chain walk
lived inside `evaluate_trust`, which is called once per machine
`VerificationEvidence`. A specification with `relationship: human_approval`
produces no evidence, so `_assess` never ran for it — and what the convergence
kernel received instead was `TrustVerdict(True, "AUTHORITY_PRESENT")`, asserted
whenever the policy, root and registry merely *existed*.
`_project_trust_gaps` only checked that the pinned genesis appeared somewhere
in the chain, not that every transition was authorized. A false-convergence
path.

## Decisions

### 1. Authority trust is separated from evidence trust

`evaluate_authority_trust()` is a new pure function holding everything
decidable about authority **without an evidence run**: policy schema and
commitment, predicate commitments, the root's own digest, the root against the
current policy, the full predecessor chain, the pinned genesis, historical
policy resolution, each transition's own bound evidence, transition predicates,
successor commitments, cycle detection.

`evaluate_trust()` keeps only what is about a particular run: the evidence's
binding to the current root and policy, and `required_evidence_facts`. It takes
the already-established authority verdict through an `authority` parameter, so
the chain is walked **once per evaluation** rather than once per run. Omitting
that parameter makes it self-contained, which is what the unit cases want.

### 2. The preflight gates execution, not just the verdict

```text
load committed state
  → verified project anchor, initial admission
  → evaluate_authority_trust()
  → if not established: INVALID, zero commands executed, return
  → only now execute the declared verifications
```

An authority that cannot be established does not get to decide what runs. This
is the whole finding: *fail-closed after the fact is not the same as never
having run.*

Rejected: keeping the trust gaps where they were and merely reordering the
verdict. The verdict was already correct — it is the process spawn that had to
move behind the gate.

### 3. A broken chain is unevaluable, not unfinished

Because the authority verdict now reaches the kernel directly, a broken chain
becomes a standalone `Gap("ROOT_OF_TRUST_INVALID", …)`, which is in
`UNEVALUABLE`, so the verdict is `INVALID` with exit code 2 — for a machine
contract, a human-only contract, or a contract with nothing runnable at all.

This closes the observation the eighth-round packet reported and deliberately
left alone. It was right to leave it: the same change fixes it properly, and
fixing it separately would have been a patch on a symptom.

### 4. Authority precedence, stated because it changed behaviour

Authority is decided first, so an authority that cannot be established is
reported **instead of**, not alongside, an evidence-level reason. Two existing
cases had to be corrected to say what they mean:

- a unit case asserted `INSUFFICIENT_EVIDENCE_PROVENANCE` while supplying
  authority facts that established nothing. Under the old order the evidence
  check ran first and masked the authority failure. It now supplies holding
  authority facts, and asserts the authority failure separately;
- an end-to-end case required `ci_verified` of *both* evidence and mutation
  facts to test evidence provenance. Nothing can establish `ci_verified`, so it
  now makes the work unevaluable before anything runs. The fixture gained
  separate `required` and `required_evidence` so the case asks only what it
  means to ask.

Neither test was wrong about the property it names. Both were relying on an
order that hid a second, more fundamental failure.

## Consequences

Asserted by A108 (four cases: an ungoverned work, an unverifiable anchor and a
broken chain each execute nothing, and the control where valid authority still
executes), A109 (two: a human-only contract converges on a sound chain, and
cannot bypass a broken one) and A110 (three: `INVALID`, exit code 2 and a
standalone `ROOT_OF_TRUST_INVALID` gap, with a machine specification, a
human-only specification, and nothing runnable).

Reverting the change makes seven blocking cases fail while both controls keep
passing.

**Not covered:** `run_verification` — the `ainative verify` entry point — still
runs one declared command on request without the preflight. It produces
evidence, not a verdict, and the evaluator never reads recorded evidence; but
it is a production entry point that executes a registry-chosen command. The
preflight was scoped to `evaluate_work` because that is where the review
located the finding, and widening it is a decision a reviewer should make
rather than one taken quietly here.
