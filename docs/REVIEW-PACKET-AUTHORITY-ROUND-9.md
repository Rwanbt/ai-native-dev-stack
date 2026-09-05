# Review Packet — Authority Hardening, Round 9

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

Two P0, closed by one change, as the review prescribed. Narrow scope.

## Revision

```text
reviewed        b96cb5b
this packet     becf737
branch          spec
pull request    #16
```

## CI

```text
run 33815656951   every job green
                  Verified Work Plane V2 on ubuntu-latest and windows-latest
```

Local: 162 V2 tests OK (2 platform skips), plus 38 `ai_docs`, 40 `scripts` and
7 `hooks` tests, the three deterministic scripts, and the scope and convention
gates.

## Both reproduced against `b96cb5b`

**P0-A — execution before authority.** A registry command that writes a
sentinel file:

```text
verdict for an ungoverned work: INVALID
the registry command's side effect exists: True
```

And with a governed work whose root chain is broken:

```text
verdict: NOT_CONVERGED
gaps: ['INELIGIBLE_VERIFICATION_EVIDENCE', 'NO_VERIFICATION_EVIDENCE', 'UNVERIFIED_SPECIFICATION']
the command ran anyway: True
```

**P0-B — the human-only bypass**, reproduced by construction:

```text
_assess calls evaluate_trust:                 True
evaluate_work calls evaluate_trust directly:  False
what the kernel receives instead: trust=TrustVerdict(True, "AUTHORITY_PRESENT")
```

A `human_approval` specification produces no evidence, so `_assess` never runs
for it, and `_project_trust_gaps` only checked that the pinned genesis appeared
somewhere in the chain.

## The correction — one abstraction, as asked

`evaluate_authority_trust()` holds everything decidable about authority without
an evidence run. `evaluate_trust()` keeps only the evidence-specific checks and
takes the established verdict, so the chain is walked once per evaluation
rather than once per run.

```text
load committed state
  → verified project anchor, initial admission
  → evaluate_authority_trust()
  → if not established: INVALID, zero commands executed, return
  → only now execute the declared verifications
```

Decisions and rejected alternatives: [ADR-0008](adr/0008-authority-preflight.md).

## The round-8 observation is closed by the same change

A broken chain is now a standalone `ROOT_OF_TRUST_INVALID` gap — `INVALID`,
exit code 2 — for a machine contract, a human-only contract, or a contract with
nothing runnable. Reporting it rather than patching it separately was the right
call: this change fixes it properly.

## A precedence change, and two tests it corrected

Authority is decided first, so an authority that cannot be established is now
reported **instead of** an evidence-level reason. Two existing cases relied on
the old order and were masking a second, more fundamental failure:

- a unit case asserted `INSUFFICIENT_EVIDENCE_PROVENANCE` while supplying
  authority facts that established nothing. It now supplies holding authority
  facts and asserts the authority failure separately;
- an end-to-end case required `ci_verified` of *both* evidence and mutation
  facts in order to test evidence provenance. Nothing can establish
  `ci_verified`, so that now makes the work unevaluable before anything runs.
  The fixture gained separate `required` and `required_evidence`.

Neither test was wrong about the property it names. Both were relying on an
order that hid something worse.

## The new cases are not vacuous

Reverting the change:

```text
FAIL  A108  an ungoverned work executes nothing
FAIL  A108  an unverifiable anchor executes nothing
FAIL  A108  a broken root chain executes nothing
FAIL  A109  a human-only contract cannot bypass the root chain
FAIL  A110  with a machine specification
FAIL  A110  with a human-only specification
FAIL  A110  with no runnable evidence at all
```

Controls green throughout: valid authority still executes its command, and a
human-only contract still converges on a sound chain.

## Exact files changed

```text
ainative_workplane/trust.py       evaluate_authority_trust(); evaluate_trust
                                  reduced to evidence checks + `authority` param
ainative_workplane/evaluator.py   preflight before execution; the authority
                                  verdict reaches the kernel
tests/test_workplane_authority.py        sentinel_command(), human_only_contract(),
                                         required_evidence
tests/test_workplane_authority_origin.py A108, A109, A110
tests/test_workplane_adversarial.py      A07 precedence
docs/adr/0008-authority-preflight.md, ARCHITECTURE.md, THREAT_MODEL.md, DoD
```

## Not covered, deliberately

`run_verification` — the `ainative verify` entry point — still runs one
declared command on request without the preflight. It produces evidence rather
than a verdict, and the evaluator never reads recorded evidence; but it is a
production entry point that executes a registry-chosen command. The preflight
was scoped to `evaluate_work` because that is where the review located the
finding. **If you want the gate widened, say so** — I did not want to widen the
architecture unasked in a round that was meant to be narrow.

## Status

```text
P0 authority = not self-certified
P1 authority = not self-certified
REUSABLE_ATTESTED_EVIDENCE = NOT BUILT
SELECTIVE_RERUN            = NOT BUILT

HISTORICAL = OPEN, no blind case run
PILOT      = OPEN, no two-harness pilot run

PRODUCTION = NO-GO
MERGE spec -> main = NO-GO
```
