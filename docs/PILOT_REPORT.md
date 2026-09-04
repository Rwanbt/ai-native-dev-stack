# Real two-harness pilot

Five real, mergeable changes to this repository, each governed by the Verified
Work Plane and measured through `evaluate_work()`. Not fixtures: every one
fixes something that was actually wrong, and all five have landed on `spec`.

    pilot_id        spec-v1-two-harness
    surface         evaluate_work
    authority       production_boundary
    pilot_evidence  true      (the instrument refuses to say this otherwise)
    raw record      docs/qualification/pilot-run-spec-v1.json

## The five items

| kind | harness | what it fixed | EMP |
|---|---|---|---|
| feature | Claude Code | `ainative work admit` — the documented flow had no surface for its middle step | EMP-003 |
| feature | OpenCode | full verification output kept beside the run record | EMP-007 |
| bugfix | OpenCode | malformed user input refused instead of stack-traced | EMP-004 |
| refactor | Claude Code | `traceability.analyze` 71 LOC / ~32 branches → 16 / 1 | EMP-009 |
| hotfix | OpenCode | the five subcommands that shipped with no help text | EMP-005 |

Claude Code 2 items, OpenCode 3. Both are real harnesses driving real edits;
neither is a string in a config file.

## Measurements

| item | verdict | runs | verification | convergence | revisions | mutations | contract intact |
|---|---|---|---|---|---|---|---|
| feature / claude-code | CONVERGED | 1 | 3 972 ms | 6 165 ms | 1 | 0 | yes |
| feature / opencode | CONVERGED | 1 | 522 ms | 2 786 ms | 1 | 0 | yes |
| bugfix / opencode | CONVERGED | 1 | 1 880 ms | 3 957 ms | 1 | 0 | yes |
| refactor / claude-code | CONVERGED | 1 | 696 ms | 2 875 ms | 1 | 0 | yes |
| hotfix / opencode | CONVERGED | 1 | 326 ms | 2 527 ms | 1 | 0 | yes |

    converged            5 / 5
    false CONVERGED      0
    false NOT_CONVERGED  0
    approvals            1 per item (creation admission), 0 further
    normative mutations  0
    repository corruption none      contract corruption none

## Friction, honestly

Nine manual interventions across five items. Every one is worth naming, because
a pilot that reports only the happy path measures nothing.

- **The edit hook.** OpenCode's `update_on_edit` plugin crashed on every write
  (`.stdin is not a function`). Edits landed on retry, but three failures per
  item is noise a real user would not tolerate. Harness-side, not plane-side.
- **A dispatch that did nothing.** OpenCode's first attempt at the bugfix
  explored the repository and made no edit. A second, more directive prompt
  landed it. Harness-side.
- **A latent defect the suite did not catch.** OpenCode's first version of the
  output feature bound `stdout` inside the `try`, so a timeout under a
  `runs_dir` raised `NameError` instead of recording `TIMEOUT`. The existing
  tests passed, because the timeout test does not set `runs_dir` — and
  `evaluate_work` always does, so one slow verification would have taken down
  a whole evaluation. Recorded as EMP-008, reproduced, fixed, regression added.
  This is the pilot earning its cost.
- **Operator error.** A `git checkout` of mine destroyed a harness edit; it was
  restored verbatim. Counted.
- **Directory scopes.** The first contract declared `execution_scope` as
  directories and was refused `SECURITY_REJECTED` — a correct refusal wearing a
  misleading name, since a directory is a wrong kind of path, not an attack.
  Recorded as EMP-006.
- **The anchor does not hand back what it pins.** A project's second work needs
  the exact approval-root artifact, and nothing in the API or CLI returns it.
  The operator must have kept it. Feeds EMP-003.

## What this decides about scalability

`REUSABLE_ATTESTED_EVIDENCE` and `SELECTIVE_RERUN` are **POST-V1**, on measured
grounds rather than preference.

    worst observed convergence          6 165 ms
    worst observed verification         3 972 ms
    whole five-item pilot               18.3 s of convergence
    redundant reruns measured           H01 re-ran 2 unchanged specs on each of
                                        3 evaluations: 8 of 12 runs, ~1 s total

Every `evaluate_work()` re-runs every declared verification. At the scale the
pilot and H01 actually exercised, the waste is about a second, and nothing was
unusable or prohibitive. That does not make the ceiling imaginary — a work with
many slow verifications would feel it — but a production blocker has to be
demonstrated, and this one was not. Backlog, with the data above as its
justification.
