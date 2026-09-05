# Final qualification packet — `spec`

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

    repository   Rwanbt/ai-native-dev-stack
    branch       spec  (PR #16)
    candidate    27a5fd655a4dee3420396e0e56bdbc241a18b68e
    CI run       33872777281, all jobs green on that exact SHA
    date         2026-09-04

## Gates

    AUTHORITY     CLOSED    external adversarial review, 10 rounds, P0=0 P1=0, frozen
    HISTORICAL    PASSED    3 conclusive cases, 0 false CONVERGED
    PILOT         PASSED    5 real items, 2 real harnesses, pilot_evidence = true
    EMPIRICAL     P0 = 0    P1 = 0
    CI            GREEN     18 jobs, 3 OS families, Python 3.8-3.13
    INSTALL       PASSED    clean venv, console entry point, no PYTHONPATH magic
    DOCS          CURRENT
    EXT. REVIEW   P0 = 0    P1 = 0  (OpenCode / z-ai-glm-4.6)

## Historical validation

| case | project | category | classification |
|---|---|---|---|
| H01 | HireLens | integration / orchestration invariant | **DETECTED** |
| H02 | Seno Dynama | exposed state surface / audio-thread contention | **DETECTED** |
| H03 | Seno Materia | cross-platform GPU, FFI safety, resource release | **INDIRECTLY_EXPOSED** |

    false CONVERGED      0
    false NOT_CONVERGED  0
    protocol             H02, H03 sealed mechanically (seal -> record -> reveal)
    discarded            1 repository, BLINDNESS_COMPROMISED before use

Twice the plane named a defect from requirements alone while the project's own
suite was fully green — 28, 101 and 46 passing tests across the three cases.

H03 is classified strictly and is the most informative result. The contract did
not name the sealed defect; it placed a finding at `renderer.rs:64` while the
sealed panic sits at `renderer.rs:77`, same function, same class of fault. The
ticket also carried a no-memory-leak requirement for which I wrote no
specification at all. Defect representable: yes. Contract insufficient: yes.
Engine wrong: no. Analysis in `docs/HISTORICAL-VALIDATION-REPORT.md`.

## Pilot

    pilot_id   spec-v1-two-harness      surface   evaluate_work
    harnesses  Claude Code (Opus 5), OpenCode (MiniMax-M3)

| kind | harness | verdict | verification | convergence |
|---|---|---|---|---|
| feature | claude-code | CONVERGED | 3 972 ms | 6 165 ms |
| feature | opencode | CONVERGED | 522 ms | 2 786 ms |
| bugfix | opencode | CONVERGED | 1 880 ms | 3 957 ms |
| refactor | claude-code | CONVERGED | 696 ms | 2 875 ms |
| hotfix | opencode | CONVERGED | 326 ms | 2 527 ms |

    5/5 CONVERGED   0 false CONVERGED   0 false NOT_CONVERGED
    1 contract revision each, 0 normative mutations, 0 corruption
    9 manual interventions, every one itemised in docs/PILOT_REPORT.md

All five items are real, useful and landed on `spec`. None was invented for the
pilot.

## EMP findings

| id | title | severity | status |
|---|---|---|---|
| EMP-002 | evidence recorded a zero-length execution window | P2 | FIXED, non-vacuity proven |
| EMP-003 | no CLI surface for work admission; documented flow dead-ended | P1 | FIXED, `ainative work admit` |
| EMP-004 | CLI stack-traced on malformed user input | P1 | FIXED |
| EMP-005 | five subcommands shipped with no help text | P2 | FIXED |
| EMP-006 | a directory in `execution_scope` is reported `SECURITY_REJECTED` | P2 | OPEN, documented |
| EMP-007 | verification output discarded; audit trail could not explain a failure | P2 | FIXED |
| EMP-008 | `NameError` on a verification timeout under `runs_dir` | P1 | FIXED, regression added |
| EMP-009 | `traceability.analyze` above the project's own blocking complexity | P2 | FIXED, gated in CI |

EMP-008 is the pilot earning its cost: introduced by a harness, passing the
existing suite, and fatal to any evaluation whose verification timed out —
because `evaluate_work` always sets `runs_dir`.

Analysed and rejected, not a defect: the substance floor does not bind on an
already-failing run, because `exit != 0` always yields `FAIL` and the run is
ineligible regardless.

## Scalability decision

    REUSABLE_ATTESTED_EVIDENCE = POST-V1
    SELECTIVE_RERUN            = POST-V1

Decided on measurement, not preference. Worst observed convergence 6 165 ms;
worst verification 3 972 ms; the whole five-item pilot 18.3 s. H01 re-ran two
unchanged specifications on each of three evaluations — 8 of 12 runs redundant,
about a second of waste. Real ceiling, not a production blocker.

## Cross-platform and installability

    CI matrix   ubuntu-latest, windows-latest, macos-latest
    Python      3.8, 3.9, 3.11, 3.13
    tests       185 passed, 2 skipped, 53 subtests
    install     pip install . into a clean venv; `ainative` entry point works
    surfaces    trust bootstrap/show, work new/admit/validate/update, verify,
                converge, debug run-command
    failure     every invalid path exits 1 or 2 with a message; none crash

## Security and observability

Authority frozen after external closure. Every production surface runs the same
authority preflight; `ainative debug` is non-authoritative by construction and
says so in its own help. Run records now carry the full verification output
beside them, digest-verifiable, so an audit trail explains a failure without
re-running it.

## Known limitations

- Genesis trust is inside the TCB. **Bootstrap trust before a controlled agent
  has repository access** — a deployment requirement, not a detail (ADR-0006).
- `git_reviewed` and `ci_verified` predicates are declared and unimplementable
  locally; only `signature` and `recorded_owner_ack` are usable.
- Every `evaluate_work()` re-runs every declared verification.
- The trust anchor pins an approval root by digest but does not hand the
  artifact back; a project's second work must already hold it.
- `main()` catches `ValueError` and `OSError` broadly, so an internal defect
  could present as a refusal rather than a crash. Deliberate for a CLI; the
  message is preserved.
- The plane verifies what the contract declares. H03 shows what that costs when
  a requirement carries no specification.

## Residual P2, accepted

EMP-006; the broad `ValueError`/`OSError` catch; `_valid_root_chain` applying
current authority facts to historical roots (no reproducer known, recorded since
round 7).

## External sign-off

    reviewer   OpenCode, model z-ai/glm-4.6, independent context
    scope      DoD claims, cli.py, evaluator.py, runner.py, traceability.py
    result     P0 = 0, P1 = 0

One claim was raised — that `verified_requirements` is not passed to
`_task_edges` and that `_scope_gaps` receives mismatched arguments. Both are
false: `traceability.py:214` passes it and `:217` matches the signature at
`:63`, and 185 passing tests would not survive the `NameError` claimed.
Rejected with evidence rather than accepted.

## Rollback

Every change is an additive commit on `spec`; `main` is untouched. The five
pilot items are independent and individually revertible. The only change to
existing verdict-path behaviour is EMP-008's `stdout = stderr = ""`
initialisation, which restores the pre-existing TIMEOUT path.

## Verdict

    PRODUCTION = GO
    MERGE-READY = YES

Merge to `main` is not performed: it was not authorised.

---

## Status addendum — 2026-09-05

Merged to `main` via PR #16 (merge commit `56e9b256b014b1f1e8d9110910875c28f442b4d5`),
and the post-promotion CI run
[33927765004](https://github.com/Rwanbt/ai-native-dev-stack/actions/runs/33927765004)
is green on that merge commit. The "Rollback" section above states `main` is
untouched, and the verdict states "Merge to `main` is not performed" — those
sentences record the state at qualification time and are superseded by this
note. The rest of this packet describes the qualified candidate and is
unchanged.
