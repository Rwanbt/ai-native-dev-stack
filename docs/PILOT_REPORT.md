# Verified Work Plane V2 — Historical Validation Checkpoint

This report records the deterministic pre-pilot gate. It is not evidence of a
real production pilot; no external harness was executed.

## Reproducible scenarios

`python scripts/workplane_structural_regression.py` executes two synthetic
structural checks:

1. A requirement with no task must produce `REQ_WITHOUT_TASK`.
2. Direct mutation of a committed artifact must produce `UNEXPECTED_MUTATION`.

Both pass against the current `spec` branch. Neither is a historical incident,
and this script is not the blind historical validation — see
[the protocol](verified-work-plane-v2-historical-validation-protocol.md), which
has never been executed. The real pilot required by the plan (two features, one
bugfix, one refactor and one hotfix, driven by two actual AI harnesses) remains
pending.

`scripts/workplane_pilot.py` was rewritten after the authority closure review,
which added a requirement the old harness did not meet: **the pilot must
exercise the authoritative production surfaces.** The old one called the pure
`converge()` kernel with a hand-built trust verdict and a hand-built freshness
result, created a non-normative artifact rather than a contract, and reported
`CONVERGED` five times. It measured nothing about authority and could not have
failed.

The replacement is an instrument, not a source of work:

- every verdict comes from `evaluate_work()`. It imports no `converge`, no
  `evaluate_trust`, no `FreshnessResult`, no `VerificationRunner` — and
  `tests/test_workplane_pilot.py` asserts that structurally, because a comment
  saying so is not a guarantee;
- **measured** and **declared** are kept apart. Whether a verdict was *correct*
  is not observable from inside; the plan declares expectations and friction,
  the instrument measures verdict, gaps, runs, durations, contract revisions,
  the approvals the work actually needed, contract integrity and repository
  state;
- it **refuses to call itself pilot evidence** unless the plan meets the
  protocol: the five kinds, at least two distinct harnesses, nothing synthetic,
  no measurement error, and a declared expectation per item so a false verdict
  is detectable. The refusals are listed in the record.

`python scripts/workplane_pilot.py --self-check` measures one governed work built
on the spot, to show the instrument working. That output is labelled
`pilot_evidence: false` and lists why. **No plan has been run.** Closing the
pilot gate needs five real work items through at least two real harnesses.

`python scripts/workplane_harness_matrix.py` exercises the same five-item shape
through two independent local harnesses (direct API and CLI facade). Both pass;
the result remains explicitly marked `external_harness: false`.
