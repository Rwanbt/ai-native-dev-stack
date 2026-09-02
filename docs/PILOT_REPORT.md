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

`python scripts/workplane_pilot.py` now executes the five-item local pilot shape
(two features, one bugfix, one refactor and one hotfix) through create → mutate →
argv verification and emits metrics. Its output is explicitly marked
`external_harness: false`; it is a deterministic local gate, not a claim of
production-harness success.

`python scripts/workplane_harness_matrix.py` exercises the same five-item shape
through two independent local harnesses (direct API and CLI facade). Both pass;
the result remains explicitly marked `external_harness: false`.
