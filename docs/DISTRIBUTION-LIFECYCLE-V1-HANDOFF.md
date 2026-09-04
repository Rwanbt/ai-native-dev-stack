# Distribution & Lifecycle v1 — handoff

Written to survive the session that produced it. Everything a next agent or a
human needs to finish this, in the order they need it.

---

## 1. Where things stand

| | |
|---|---|
| Branch | `feat/distribution-lifecycle-v1` |
| Base | `spec` @ `2381abb` (not an ancestor of `main`; `main` is 0 commits ahead of `spec`) |
| PR | [#17](https://github.com/Rwanbt/ai-native-dev-stack/pull/17) — **open, not merged** |
| HEAD at handoff | `4db8342` |
| Verdict | **not yet rendered** — see §4 |

Read in this order: `docs/adr/0009-distribution-profiles-and-lifecycle-ownership.md`
(the decisions), then `docs/DISTRIBUTION-LIFECYCLE.md` (the operating manual),
then `ainative/lifecycle/`.

---

## 2. What is done

The whole product is built and green. Two profiles resolved by declarative
inheritance, ownership recorded with a SHA-256 per managed file, transactional
mutations with the install state committed last, non-destructive downgrade,
uninstall and purge, updates with rollback, legacy adoption, `doctor`/`repair`,
and a concurrency lock.

| Gate | Result | How to re-run |
|---|---|---|
| Lifecycle suite | 173 tests green locally | `python -m unittest tests.test_lifecycle_matrix tests.test_lifecycle_ownership tests.test_lifecycle_security tests.test_lifecycle_transactions tests.test_lifecycle_update tests.test_lifecycle_cli` |
| Non-vacuity | 33/33 guards proved necessary | `python scripts/lifecycle_non_vacuity.py` |
| Clean install E2E | green, from a wheel with no checkout | `python scripts/lifecycle_clean_install.py` |
| Dogfood | not re-run after EMP-LC-041 | `python scripts/lifecycle_dogfood.py --output docs/qualification/lifecycle-v1-dogfood.json` |
| Complexity budget | 0 findings / 445 functions | `python scripts/check_complexity_budget.py` |
| LOC gate | 34 files, 0 warnings | `cd ainative && node ../hooks/pretool-loc-gate/run_gate.js --all` |
| Scope + conventions | green | `python scripts/measure_scope.py && python scripts/validate_conventions.py` |
| Work Plane | not re-run; no Work Plane source file modified | see `.github/workflows/ci.yml`, job `workplane-v2` |
| CI | `d3b1276` failed Windows py3.11 only because EMP-LC-036 still assumed timestamp uniqueness; replacement candidate pending | `gh pr checks 17` |

---

## 3. What is left — the only remaining work

**The independent review has not converged.** That is the single thing between
this branch and a verdict.

The closed list now reaches EMP-LC-041. Round 8 is the next bounded pass; it must
use the closed-findings list below and may only reopen a finding with a new
reproducer.

### The loop to close it

```bash
# 1. Run a review round. The prompt that has been working is the one with the
#    closed-findings list, so the reviewer spends its budget on new ground.
codex exec --skip-git-repo-check "$(cat <the review prompt>)" > review-N.txt 2>&1

# 2. For EVERY finding: reproduce it first. Do not fix on the report alone.
#    Two findings so far were FALSE and were rejected with evidence.
python <a reproducer script>

# 3. TRUE  -> fix + regression test + a non-vacuity case if it is a guard
#    FALSE -> reject, and say why in the packet

# 4. Re-run every gate in §2, then push.

# 5. If the round returns new P0/P1, fix and run the focused regression round.
# 6. If it returns no new P0/P1, run one confirmatory assertion pass only.
# 7. Close external review when the bounded round and confirmatory/focused pass
#    both return P0 = 0 and P1 = 0. Residual P2 are recorded, not an automatic
#    reason to launch another full review.
```

Convergence is bounded: P0 and P1 are blockers; P2 is non-blocking unless a
concrete release-critical reason is recorded. For EMP-LC-038, bounding `undo()`
by the PREPARED plan protects against corrupt, partial or inconsistent journals.
It does not turn the journal into an adversarial trust boundary: an actor already
able to arbitrarily modify lifecycle journals inside the project may also be able
to modify the project files themselves.

The review prompt lives at
`<scratchpad>/review-prompt-4.md`; if it is gone, rebuild it from §92 of the
original mandate plus the closed-findings list in §5 below.

### Then, to finish

1. Update `docs/DISTRIBUTION-LIFECYCLE-V1-QUALIFICATION.md` — it is written but
   predates the last 12 findings. Refresh: the SHA, the gate table, the
   EMP-LC list, the review dispositions, and the verdict.
2. Confirm CI green on the final SHA (`gh pr checks 17`).
3. Render the verdict. `PRODUCTION = GO` only if P0 = 0, P1 = 0 **and** a review
   round produced no new finding.

**Do not merge.** The mandate withheld that authority and it should stay
withheld until a human has read the qualification packet's §11 (review) and §12
(known limitations).

---

## 4. Why the verdict is not rendered

Because a review round that still finds real defects is evidence the work is not
finished, and no amount of green gates substitutes for it. Rounds 5 and 6 each
found P0-class defects — silent destruction of user content — in code whose full
suite was green at the time. Declaring GO after round 6 would be declaring it on
the strength of tests that had already failed to see six such defects.

---

## 5. Documented EMP-LC findings

Every one reproduced before it was touched, fixed, and covered by a regression.
Severity is my own assessment, stated even where it differed from the reporter's.

| ID | Sev | Defect |
|---|---|---|
| EMP-LC-001 | P2 | a declared data root with no content yet reported `MISSING`, so a healthy fresh Verified install exited non-zero |
| EMP-LC-002 | P2 | an uninstall plan reported a managed *region* removal as a file removal |
| EMP-LC-003 | P2 | `apply`/`remove` on an external block were not exact inverses |
| EMP-LC-006 | P1 | a transaction backed up with `copy2`, so `--purge` on a data root raised `PermissionError` |
| EMP-LC-007 | **P0** | legacy adoption recorded a customised file at its on-disk digest, letting the next install overwrite it |
| EMP-LC-008 | P2 | `--force-unlock` retried without removing the lock |
| EMP-LC-009 | P1 | a prompt on a stdin claiming a terminal then returning EOF raised a traceback |
| EMP-LC-010 | **P0** | purging a project with backups told the applier to back up the backup directory into itself |
| EMP-LC-011 | P2 | the suite compared paths against `mkdtemp`'s answer while the CLI resolves (test-only) |
| EMP-LC-012 | P1 | pruning removed the file and kept its state record, leaving `doctor` permanently unhealthy |
| EMP-LC-013 | P1 | the no-op branch of `install` committed the profile without the lock |
| EMP-LC-014 | P1 | `update rollback` restored what was replaced and left what was created |
| EMP-LC-015 | P2 | tree components skipped the case-fold collision check |
| EMP-LC-016 | P1 | `profile purge verified` had no interrupted-transaction gate |
| EMP-LC-017 | P2 | rollback metadata was a second record written after the commit |
| EMP-LC-018 | **P0** | `--purge` deleted a managed file the user had edited, against the retention table |
| EMP-LC-019 | P1 | a tampered journal id made `repair` write outside the project root |
| EMP-LC-020 | P2 | the purge emptied `.ai-native/lifecycle/` with `rmtree` |
| EMP-LC-021 | **P0** | the same defect as 018, in the orphan path I had not grepped |
| EMP-LC-022 | P2 | the purge still `rmtree`'d the journal subdirectories |
| EMP-LC-023 | P2 | an adopted external region was recorded as not written by us |
| EMP-LC-024 | P1 | `update --dry-run` wrote `.new` files and the update cache |
| EMP-LC-025 | P1 | text mode translated CRLF, rewriting every line of a file we do not own |
| EMP-LC-026 | P2 | a marker quoted in prose opened a managed region |
| EMP-LC-027 | P2 | a hostile `check_interval` crashed the updater |
| EMP-LC-028 | P2 | a marker quoted inside the block closed it early |
| EMP-LC-029 | P1 | `bool("false")` is `True`, and that flag gates a deletion |
| EMP-LC-030 | P1 | the lock's payload was written after `O_EXCL`, so a mid-creation lock was deleted |
| EMP-LC-031 | P1 | a killed transaction persisted no `completed_changes` |
| EMP-LC-032 | P1 | `undo` overwrote a file edited after the interruption |
| EMP-LC-033 | P2 | markers were anchored at the start of a line but not the end |
| EMP-LC-034 | P1 | a write that raised after landing escaped the rollback |
| EMP-LC-035 | P2 | `.new` files survived an update that failed |
| EMP-LC-036 | P1 | after `--force-unlock`, the old owner's release deleted the new owner's lock |
| EMP-LC-037 | P1 | update staging overwrote an existing user-owned `.new` file, destroying content the stack does not track |
| EMP-LC-038 | P1 | undo trusted a completed journal record for a path the PREPARED plan never named |
| EMP-LC-039 | P2 | a refused lock unlink escaped as a raw `OSError` instead of an actionable lifecycle error |
| EMP-LC-040 | P2 | repair rewrote state after dropping orphaned records without first preserving a recoverable copy |
| EMP-LC-041 | P1 | two acquisitions with the same serialized metadata were indistinguishable, so the old owner could release the replacement lock |

### Rejected, with evidence

- A forged `CREATE` record in a committed journal does not reach `undo`:
  `rollback_candidate` requires a state backup the forgery lacks.
- An END marker *after* the block does not close it early; the arrangement that
  does requires editing inside the managed region, and the anchoring fix covers
  it anyway.

---

## 6. Things a next agent will otherwise re-learn the hard way

1. **After a fix, grep for the same root cause.** EMP-LC-021 is EMP-LC-018 in a
   second location. AGENTS.md §8 says to do this; skipping it cost a P0.
2. **A layered guard measures badly.** Five non-vacuity cases were VACUOUS at
   first because removing one layer proved nothing — the next still refused. A
   case must remove the *whole* protection or it measures redundancy.
3. **A test can be blind to what it claims to prove.** `commit_state_last` went
   vacuous the moment rollback learned to restore the state; interrupting by
   exception no longer showed the ordering. It had to model a *kill*.
4. **Cast is not type-check.** `bool("false")` is `True`; `int("soon")` raises.
   Both reached code that deletes or that a user runs daily.
5. **`Path.write_text` translates newlines on Windows.** A fixture written as LF
   landed as CRLF, and only symmetric translation on read hid it.
6. **A temp path is not its resolved form** — `/private/var` on macOS,
   `RUNNER~1` on Windows CI. The suite passed locally and failed on both.
7. **The restricted Windows sandbox cannot run temporary-file gates**
   (`PermissionError` creating temp dirs); use an unsandboxed runner for those
   gates. CI must still be bound to the exact pushed candidate SHA.
8. **`acquired_at` is observability, not lock identity.** CI run `33917366196`
   proved two claims can share it. EMP-LC-041 adds a UUID `claim_id`; tests
   must assert that identity rather than clock precision.

---

## 7. Files that matter

```
ainative/cli.py                     the dispatcher; imports the Work Plane lazily
ainative/lifecycle/planner.py       removal_change() — the single deletion decision
ainative/lifecycle/transaction.py   outcome -> journal -> perform; undo() checks digests
ainative/lifecycle/state.py         every field that gates a deletion is typed here
ainative/lifecycle/external.py      whole-line markers, no newline translation
ainative/lifecycle/lock.py          atomic create-with-content; owned release
scripts/lifecycle_non_vacuity.py    33 cases; STALE means a guard moved
scripts/lifecycle_clean_install.py  the only gate that runs outside the checkout
scripts/lifecycle_dogfood.py        the feature judged by the stack it installs
docs/DISTRIBUTION-LIFECYCLE-V1-QUALIFICATION.md   needs refreshing (§3)
```
