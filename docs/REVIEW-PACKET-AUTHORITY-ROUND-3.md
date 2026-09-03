# Review Packet — Authority Hardening, Round 3

Answers the review of `4c8d1c3` / `b40f510`: two P0, four P1. All six are
addressed. Nothing here is self-certified.

## Revision

```text
reviewed        b40f510 (the review read 4c8d1c3; b40f510 adds only the round-2 packet)
this packet     2a6f838
branch          spec
pull request    #16
```

## Both P0 reproduced first

| Finding | Reproduction against `b40f510` |
| --- | --- |
| Self-issued mutation approval | A failing check. The agent builds a `mutation_approval` in memory with the right target digest, policy digest and predicate, calls `mutate`, and the weakened registry is accepted. Verdict flips `NOT_CONVERGED` → `CONVERGED`. |
| Authority race | A registered command rewrites `manifest.json` to revision 99 while it runs. Verdict `CONVERGED`; manifest on disk says 99. |

The reviewer's observation that the test helper demonstrated the first attack
was correct — `approval_for()` constructed exactly that object.

## Corrections

| Finding | Correction | Case |
| --- | --- | --- |
| P0 self-issued approval | `mutate(..., approval=<path>)`. The controller reads the artifact and observes **its own** provenance. An in-memory mapping is refused by name; under `git_recorded` the approval must already be recorded; under `signature_verified` an actor without the key cannot produce one. | A91, A92 |
| P0 authority race | Authority is re-read and its commitment compared after the runs. Drift is `AUTHORITY_CHANGED_DURING_EVALUATION`, which is in `UNEVALUABLE`, so the verdict is `INVALID`. | A93 |
| P1 root rotation | `WorkController.root_history()` resolves predecessors from earlier revisions of the same work; the evaluator passes the chain. | governed path |
| P1 human-approval-only | `NO_VERIFICATION_EVIDENCE` is raised only for specifications that expect a machine run. `UNVERIFIED_SPECIFICATION` is still raised for every declared specification, so absence of an authorized approval still blocks. | `test_convergence_ignores_narrative_and_blocks_failures` |
| P1 authoring facade | `ainative work update --approval --delete`; a controller refusal is reported as a refusal. | `test_workplane_cli` |
| P1 selective rerun | Not "fixed" — **named**. ADR-0003 §1 now describes two modes: local secure (built, re-executes everything) and attested reusable (designed for, not built). The DoD carries `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT`. | ADR-0003 |

P2 notes taken: recorded runs are now called a local execution log, not an
audit trail. The mutation bar was not relaxed.

## Commits

```text
da99386  fix(workplane): make the mutation approval an artifact, and re-read authority
016388d  fix(workplane): resolve root chains, let human approval converge, carry approvals
2a6f838  docs: record the third round, and name the mode that is not built
```

## CI

Green on Linux and Windows at every commit. Local: 136 tests, 2 platform skips
that execute on the Linux leg.

Note for the reviewer: three suites failed once mid-session with `WinError 8`
(insufficient system resources) after several hundred spawned processes. Both
an isolated re-run and a full re-run passed, and CI is green. Reported because
a flake dismissed without evidence is how a real defect gets buried.

## Residual risks, restated because they are the honest answer

- Under a `git_recorded` policy an actor with commit rights can still record an
  approval. It is visible and in history, but it is not excluded. Only
  `signature_verified` excludes an actor without the key — and this build can
  verify that.
- Authority drift is compared before and after the runs, not continuously. A
  change made and reverted inside one run is undetected.
- Convergence re-executes every declared verification. For a large suite that
  is prohibitive, and the mode that would fix it is not built.

## Still open

```text
HISTORICAL   no blind case run
PILOT        no two-harness pilot run
```

## Verdict

```text
P0 = not claimable
P1 = not claimable
PRODUCTION = NO-GO
MERGE spec -> main = NO-GO
```

Three reviews have now each found real findings in what the previous round's
green cases did not ask — including one inside a correction. That is the
argument for keeping `P0 = 0` unclaimed until someone other than the author
says it.
