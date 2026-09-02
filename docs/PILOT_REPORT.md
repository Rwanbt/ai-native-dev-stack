# Verified Work Plane V2 — Historical Validation Checkpoint

This report records the deterministic pre-pilot gate. It is not evidence of a
real production pilot; no external harness was executed.

## Reproducible scenarios

`python scripts/workplane_historical_validation.py` executes two blind scenarios:

1. A requirement with no task must produce `REQ_WITHOUT_TASK`.
2. Direct mutation of a committed artifact must produce `UNEXPECTED_MUTATION`.

Both scenarios pass against the current `spec` branch. The real pilot required by
the plan (two features, one bugfix, one refactor and one hotfix) remains pending.

`python scripts/workplane_pilot.py` now executes the five-item local pilot shape
(two features, one bugfix, one refactor and one hotfix) through create → mutate →
argv verification and emits metrics. Its output is explicitly marked
`external_harness: false`; it is a deterministic local gate, not a claim of
production-harness success.
