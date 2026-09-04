# Verified Work Plane V2 — Blind Historical Validation Protocol

Status: **defined, never executed.** No historical validation evidence exists
for this branch.

## Why this document exists

`scripts/workplane_structural_regression.py` used to be named
`workplane_historical_validation.py` and described itself as executing "two
blind scenarios". It executes a synthetic `REQ_WITHOUT_TASK` gap and a
direct-mutation detection. Section 44 of the production hardening plan
excludes exactly that by name: a synthetic gap is not a historical incident.
The script was renamed to what it is, and this document holds the protocol it
was standing in for.

## What a real run requires

Each case needs all of:

- a real historical issue or ticket from this repository;
- the real pre-fix checkout, by commit;
- only the information available at that time;
- a defect known to the organiser and **hidden from the evaluator**;
- a Work Contract authored by the evaluator with no defect label;
- one V2 run against the pre-fix checkout;
- the verdict frozen and recorded before the reveal;
- the defect revealed, and the comparison recorded.

## Blindness

The evaluator who authors the contract must not have seen the known failure
label, the future fix, the future test, or the postmortem. One agent or person
cannot hold both roles: an evaluator who already knows the answer produces a
contract shaped by it, and the result measures nothing.

This is the reason the gate is still open. It is not a missing script.

## Record per case

```text
input bundle digest
pre-fix commit
contract digest
result digest
reveal timestamp
final classification
```

## Classification

```text
DETECTED
INDIRECTLY_EXPOSED
MISSED
NOT_REPRESENTABLE_FROM_ORIGINAL_REQUIREMENTS
```

`NOT_REPRESENTABLE_FROM_ORIGINAL_REQUIREMENTS` is a real outcome, not a
failure to record: a defect that no requirement available at the time could
have expressed tells you where the method's limit is.

## Current state

Zero cases run. Any statement that V2 detects historical defects is
unsupported until this table has rows.

| Case | Issue | Pre-fix commit | Classification |
| --- | --- | --- | --- |
| _none_ | | | |
