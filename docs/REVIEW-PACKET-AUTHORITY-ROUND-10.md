# Review Packet — Authority Hardening, Round 10

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

One P0 — the surface the round-9 packet flagged and declined to widen unasked.
Closed. Tiny round, as asked.

## Revision

```text
reviewed        becf737
this packet     2fb2154
branch          spec
pull request    #16
```

## CI

```text
run 33819616022   every job green
                  Verified Work Plane V2 on ubuntu-latest and windows-latest
```

Local: 168 V2 tests OK (2 platform skips), plus 38 `ai_docs`, 40 `scripts` and
7 `hooks` tests, the three deterministic scripts, and the scope and convention
gates.

## Reproduced against `becf737`

For an ungoverned work, a broken root chain, and a work never admitted — the
same result each time:

```text
ungoverned:    evaluate_work -> INVALID, side effect: False
ungoverned:    ainative verify -> exit 0, side effect: True

broken-chain:  evaluate_work -> INVALID, side effect: False
broken-chain:  ainative verify -> exit 0, side effect: True

unadmitted:    evaluate_work -> INVALID, side effect: False
unadmitted:    ainative verify -> exit 0, side effect: True
```

Converge refused and executed nothing. Verify executed **and returned success.**
The exit code was the part I had not anticipated when I reported the gap.

## The correction

`establish_authority(work_dir, repository_root) -> AuthorityContext` — one
boundary, starting no process, establishing committed state, the verified
project anchor, project governance, the initial admission, the current policy
and root, the complete chain, the historical policy chain, each transition's
own evidence, and the authority provenance.

```text
run_verification(...)          evaluate_work(...)
  → establish_authority()        → establish_authority()
  → refuse unless established    → refuse unless established
  → _run_established(ctx, uid)   → for each machine spec: _run_established(ctx, uid)
```

`_run_established` is internal, so the chain is walked **once per evaluation**
rather than once per specification — which also removes a repeated authority
load that was already there. No public parameter skips the gate; A111 asserts
`run_verification` accepts exactly `work_dir`, `repository_root`,
`specification_uid`.

`ainative debug run-command` stays ungated, as instructed and for the reason
given: everything it evaluates comes from the caller, and it labels its own
output `"authority": "none"`.

Amendment recorded in [ADR-0008](adr/0008-authority-preflight.md) rather than a
new record — it is the same decision finished.

## Cases

```text
A111  VerifyEntrypointTests
  verify refuses an ungoverned work                      blocking
  verify refuses a broken root chain                     blocking
  verify refuses a work that was never admitted          blocking
  the public API offers no way to skip the gate          blocking
  verify still works under valid authority               control

A112  ExecutionSurfaceTests
  converge gated, verify gated, debug run-command not    blocking + control
```

A111's refusals assert three things each: exit 2, no sentinel file, and no
recorded run. The control asserts the opposite three, including a `PASS`
verification run on disk.

Reverting the gate makes five blocking cases fail; the control keeps passing.

## Exact files changed

```text
ainative_workplane/evaluator.py   AuthorityContext, establish_authority(),
                                  _run_established(); run_verification and
                                  evaluate_work rewired through them
tests/test_workplane_authority_origin.py   A111, A112
docs/adr/0008-authority-preflight.md (amendment), ARCHITECTURE.md,
docs/THREAT_MODEL.md, docs/VERIFIED-WORK-PLANE-V2-DOD.md
```

## The P2 you named, recorded and not acted on

`_valid_root_chain` measures each *historical* root's `required_mutation_facts`
against the current authority observation, while each *transition* is measured
against its own bound evidence. No false-success reproducer is known. It is in
the DoD's residual risks rather than in this diff — widening a narrow round is
how the last two findings got their scope wrong in the first place.

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
