# Pilot Instrument — Readiness

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

The pilot harness has been rewritten to meet the closure review's requirement.
The instrument is ready; **the pilot has not been run and cannot be run without
five real work items through at least two real harnesses.**

## Revision

```text
instrument      91a7aac
branch          spec
CI              run 33822782430, green on ubuntu-latest and windows-latest
tests           185 V2 tests (2 platform skips), 18 of them the instrument's
```

## What the old harness was

```python
converge(graph, [result],
         freshness=evaluate_freshness(...),
         trust=evaluate_trust(result, policy=policy, approval_root=approval_root))
```

It called the pure kernel with a trust verdict and a freshness result it built
itself, ran the runner with a hand-built binding, and committed
`{"task": {"kind": ..., "index": ...}}` — a non-normative artifact, not a
contract. It reported `CONVERGED` five times. It measured nothing about
authority, and there was no input for which it could have failed.

## What the instrument is

Three properties, each of which the old harness lacked.

**No authority is injected.** Every verdict comes from `evaluate_work()`. The
module imports none of `converge`, `evaluate_trust`, `evaluate_authority_trust`,
`evaluate_freshness`, `TrustVerdict`, `FreshnessResult`, `VerificationEvidence`,
`VerificationRunner`, `policy_commitment`, `approval_root_commitment` — and
`InstrumentBoundaryTests` asserts that by parsing the module's imports rather
than trusting a comment.

**Measured and declared are separated.** Whether a verdict was *correct* is not
observable from inside the instrument: it needs someone who knows what the work
was supposed to do. So each item record has three blocks:

| Block | Who fills it | Contents |
| --- | --- | --- |
| `measured` | the instrument | verdict, reason, gaps, authority established and its refusal, specification count, runs, eligible runs, verification runtime, convergence wall time, contract revisions, normative mutations, root transitions, contract digest, contract integrity, both provenance observations, repository head and dirtiness |
| `declared` | the operator, before the run | expected verdict, manual interventions, reruns, friction, tokens |
| `assessed` | the instrument, from the two | verdict matches expectation, false `CONVERGED`, false `NOT_CONVERGED` |

A field the instrument cannot establish is never quietly filled in.

**It refuses to call itself pilot evidence.** `pilot_evidence` is `true` only
when the plan meets the protocol, and every refusal is listed in the record:

```text
the five kinds — two features, a bugfix, a refactor, a hotfix
at least two distinct harness_ids
nothing declared synthetic
no item the instrument failed to measure
a declared expected verdict per item, or a false verdict is undetectable
```

Running the script with a convenient plan cannot close the gate.

## Measurements against the brief

| Asked for | Where |
| --- | --- |
| final verdict | `measured.verdict` |
| gaps | `measured.gaps` (code, uid, detail) |
| number and duration of verifications | `measured.verification_runs`, `measured.verification_runtime_ms` |
| contract mutations | `measured.contract_revisions`, `measured.normative_mutations` |
| approvals needed | `measured.normative_mutations` — derived from committed state: each revision that changed the success conditions required one |
| convergence time | `measured.convergence_wall_ms` |
| false `NOT_CONVERGED` | `assessed.false_not_converged`, aggregated at the top level |
| false `CONVERGED` | `assessed.false_converged`, aggregated at the top level |
| human interventions | `declared.manual_interventions` — not observable from inside |
| harness errors / incompatibilities | `harness_error` per item, `harness_errors` aggregated |
| final repository state | `measured.repository_head`, `measured.repository_dirty` |
| no contract corruption | `measured.contract_intact` — the revision is unchanged and the committed artifacts still digest to what the revision recorded |

## The plan format

```json
{
  "pilot_id": "v2-pilot-1",
  "items": [
    {
      "kind": "feature",
      "harness_id": "claude-code",
      "provider": "claude-opus-5",
      "repository_root": "D:/App/<project>",
      "work_dir": "D:/App/<project>/.ai-native/work/<item>",
      "synthetic": false,
      "declared": {
        "expected_verdict": "CONVERGED",
        "manual_interventions": 0,
        "reruns": 0,
        "friction": null,
        "tokens": null
      }
    }
  ]
}
```

Run with `python scripts/workplane_pilot.py --plan plan.json --output record.json`.

## Self-check

`python scripts/workplane_pilot.py --self-check` builds one governed work —
project trust anchor, creation approval, real contract, real registry, real
verification — measures it through `evaluate_work()`, and reports:

```text
pilot_evidence: false
  the protocol needs ['bugfix', 'feature', 'feature', 'hotfix', 'refactor'], this plan has ['feature']
  the protocol needs at least 2 distinct harnesses, this plan has ['self-check']
  the protocol needs real work items; 1 are declared synthetic
```

That is the instrument working and declining to claim anything. CI and the
qualification harness call this mode.

## The authority freeze held

This change touches no `controller`, `trust`, `authorization`, `evaluator`,
`contracts`, `bootstrap`, `provenance` or `convergence` code. The rewrite found
no authority bug, so it fixed none.

## What is still needed, and from whom

```text
INSTRUMENT   ready
PLAN         needs five real work items — 2 features, 1 bugfix, 1 refactor, 1 hotfix
HARNESSES    needs at least two, actually doing the work
```

Neither the items nor the second harness are the instrument's to invent, and
fabricating them would be the exact failure the old harness embodied.

```text
AUTHORITY  = CLOSED
HISTORICAL = OPEN
PILOT      = OPEN
PRODUCTION = NO-GO
MERGE spec -> main = NO-GO
```
