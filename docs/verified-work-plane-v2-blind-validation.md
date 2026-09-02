# Verified Work Plane V2 — Blind Historical Validation Protocol

## Goal

Measure whether V2 catches failures without shaping the contract around their known
outcomes. A historical incident is prepared by one person; the evaluator receives only
the redacted contract, repository revision, and registered command set.

## Procedure

1. Select at least two completed incidents with retained revisions and test evidence.
2. A preparer records the original requirements, acceptance criteria, task mapping,
   relevant scope, dependencies, and the expected historical failure separately.
3. The evaluator creates the Work Contract without seeing the expected failure label.
4. Run the registered verification and convergence flow against the historical state.
5. Reveal the label only after the verdict is stored; compare detected gaps with the
   recorded failure.
6. Publish a `PILOT_REPORT.md` with false positives, missed failures, rerun cost, and
   whether the contract was changed after revelation.

## Pass criteria

- No corrupted committed contract state.
- A deliberately failing normative verification never yields `CONVERGED`.
- Supported direct normative mutation and stale scoped state are detected.
- A simple outside-scope change does not force a full rerun.

## Exclusions

Do not use post-hoc requirements or an incident whose source state cannot be restored.
These would test narrative hindsight rather than the proposed verification model.

