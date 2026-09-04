# Distribution & Lifecycle Manager v1 — qualification packet

What was built, what was proved, what was found and fixed, and what is still
true that a reader should know before merging.

---

## 1. Identity

| | |
|---|---|
| Branch | `feat/distribution-lifecycle-v1` |
| Qualified implementation SHA | `38ccd2f60e24fe895743966db092438b2a0723a2` |
| Packet finalization | documentation and equivalent-path regression pending an exact-SHA CI run |
| Base | `spec` @ `2381abb7ec46a0113056c2597d32b16bcdb86fa1` |
| Merge base | `2381abb7ec46a0113056c2597d32b16bcdb86fa1` (linear; no merges) |
| Pull request | [#17](https://github.com/Rwanbt/ai-native-dev-stack/pull/17) |
| Commits | 19 |
| Diff | 55 files, +11 536 / −434 |

**Base selection.** `2381abb` is not an ancestor of `origin/main`, and
`origin/main` is 0 commits ahead of `origin/spec`. Per the mandate's rule the
base is therefore `spec`, and the branch is linear on top of it.

---

## 2. Architecture

```
AI Native Dev Stack
        │
        ├── Standard    context · memory · skills · hooks · adapters · AI docs
        │
        └── Verified    Standard
                          + Verified Work Plane · project trust · Work Contracts
                            Verification Runner · evidence · traceability · convergence
```

```
ainative/
├── __init__.py            distribution version
├── cli.py                 top-level dispatcher; Verified commands handed over verbatim
└── lifecycle/
    ├── errors.py          stable error codes -> documented exit codes
    ├── paths.py           containment: the guard between a manifest string and unlink()
    ├── digest.py          SHA-256, and the four states a managed file can be in
    ├── manifest.py        component + profile catalogue, validated at load
    ├── source.py          where the installable payload comes from
    ├── state.py           the install state; written last in every transaction
    ├── external.py        managed regions inside files the stack does not own
    ├── planner.py         a desired profile -> an explicit list of changes
    ├── transaction.py     journal, backup, apply, verify, rollback
    ├── lock.py            one mutation at a time, with liveness-checked staleness
    ├── legacy.py          adoption of a pre-lifecycle install
    ├── installer.py       init and profile switch
    ├── uninstaller.py     uninstall, --purge, profile purge
    ├── updater.py         check, apply, rollback
    ├── provider.py        UpdateProvider: a release source and a local one
    ├── version.py         SemVer, done properly, with no dependency
    ├── recovery.py        doctor (reads) and repair (acts)
    ├── status.py          what is installed, and its health
    └── data/              profiles.json, components.json
```

**Dependency direction, enforced.** The lifecycle layer imports nothing from
`ainative_workplane`; the Work Plane imports nothing from `ainative`; the
dispatcher imports the Work Plane lazily, inside the Verified branch only.
`tests/test_lifecycle_cli.py::LayerBoundary` proves all three by inspecting
`sys.modules` in a child process, and by grepping the Work Plane's sources.

**Authority architecture untouched.** No file under `ainative_workplane/` was
modified. ADR-0001 … ADR-0008 stand. The only doc change there is a corrected
Python-version line (it said 3.8+ while the package required 3.11).

---

## 3. Profile manifests

`ainative/lifecycle/data/profiles.json`:

```
standard   extends: null      8 components
verified   extends: standard  3 components, declared once, never restating standard
```

`effective_components(verified)` = the 8 Standard components followed by the 3
Verified ones. The resolver refuses an unknown profile, an unknown parent, an
unknown component id, and an inheritance cycle.

## 4. Component model

| Component | Profile | Kind | Ownership | Destination |
|---|---|---|---|---|
| `ai-docs-tooling` | standard | tree | MANAGED_IMMUTABLE | `tools/ai_docs/` |
| `engineering-method` | standard | file | MANAGED_MUTABLE | `AGENTS.md` |
| `conventions` | standard | file | MANAGED_MUTABLE | `conventions.json` |
| `context-template` | standard | tree | MANAGED_IMMUTABLE | `.ai-native/templates/` |
| `skills-claude` | standard | tree | MANAGED_IMMUTABLE | `.claude/skills/` |
| `skills-agents` | standard | tree | MANAGED_IMMUTABLE | `.agents/skills/` |
| `machine-config` | standard | template | USER_DATA | `tools/ai_docs/config.sh` |
| `gitignore-entry` | standard | external_block | EXTERNAL_CONFIG | `.gitignore` |
| `verified-workplane` | verified | marker | MANAGED_IMMUTABLE | `.ai-native/lifecycle/verified.json` |
| `verified-guide` | verified | file | MANAGED_IMMUTABLE | `.ai-native/docs/VERIFIED-WORK-PLANE.md` |
| `verified-data` | verified | data_root | USER_DATA | `.ai-native/{trust,work,runs}` |

## 5. Ownership model

Four classes, and a SHA-256 recorded per managed file at the moment the stack
writes it. Comparing that digest with the bytes on disk yields `UNCHANGED`,
`USER_MODIFIED`, `MISSING` or `CONFLICT`, and every destructive decision reads
that answer. `created_by_ainative` is separate and stronger: a file adopted
because it sat where a managed file goes, but whose bytes the stack never
wrote, is never replaced and never removed by any operation, `--purge`
included.

## 6. Transaction model

```
inspect → plan → validate → backup → stage → apply → verify → commit state
                                                              └── last, always
```

Journal at `.ai-native/lifecycle/transactions/<id>.json`, states
`PREPARED → APPLYING → COMMITTED | ROLLED_BACK`, with `APPLYING` on disk read as
`INTERRUPTED`. The install state is backed up alongside the files, so an undo
restores the record as well as the bytes. Reversal is one operation shared by
`repair` and `update rollback`: restore what was replaced, remove what was
created, put the state back.

---

## 7. Gate results

The implementation baseline was executed at `38ccd2f`. The two final P2 closure
changes were then validated locally on the packet-finalization tree; its exact
CI run is the remaining gate.

| Gate | Result | Evidence |
|---|---|---|
| PROFILE MODEL | **PASS** | `test_lifecycle_ownership.OwnershipDeclarations`, `test_lifecycle_cli.LayerBoundary` |
| STANDARD INSTALL | **PASS** | `test_none_init_standard_installs_standard` + clean-install E2E |
| VERIFIED INSTALL | **PASS** | `test_none_init_verified_installs_verified`, `…does_not_write_any_authority_artifact` |
| STANDARD → VERIFIED | **PASS** | `test_standard_switch_verified_adds_only_the_delta` |
| VERIFIED → STANDARD | **PASS** | `test_verified_switch_standard_preserves_the_audit_trail` |
| ROUND TRIP | **PASS** | `test_round_trip_none_standard_verified_standard_verified` (byte-for-byte history) |
| OWNERSHIP | **PASS** | `test_lifecycle_ownership` — 23 tests |
| USER DATA PRESERVATION | **PASS** | `test_an_edit_survives_install_update_downgrade_and_uninstall` |
| UNINSTALL | **PASS** | `test_uninstall_removes_unchanged_managed_files_and_keeps_the_rest` |
| PURGE | **PASS** | `test_uninstall_purge_removes_verified_data_and_keeps_unrelated_files`, `test_purge_still_keeps_a_managed_file_the_user_edited` |
| LEGACY MIGRATION | **PASS** | `test_lifecycle_transactions.LegacyAdoption` — 5 tests |
| UPDATE CHECK | **PASS** | `test_lifecycle_update.UpdateCheck` — 8 tests |
| UPDATE APPLY | **PASS** | `test_lifecycle_update.UpdateApply` — 7 tests |
| UPDATE RECOVERY | **PASS** | `test_lifecycle_update.UpdateRecovery` — 6 tests |
| DRY RUN | **PASS** | `test_every_mutation_supports_dry_run_and_writes_nothing` (whole-tree digest before/after) |
| REPAIR | **PASS** | `test_lifecycle_transactions.TransactionSafety` — 11 tests |
| PATH SAFETY | **PASS** | `test_lifecycle_security` — 35 tests |
| CONCURRENCY | **PASS** | `test_lifecycle_transactions.Locking` — 15 tests, including fixed-time claim identity, serialized replacement and equivalent-path identity |
| CROSS PLATFORM | **PASS** | CI: 3 OS × 2 Pythons, all lifecycle suites |
| CLEAN INSTALL | **PASS** | `scripts/lifecycle_clean_install.py`, 3 OS in CI |
| EXISTING VERIFIED SUITE | **PASS** | 187 Work Plane tests, no source file modified |
| ANTI-DEBT | **PASS** | complexity 0 findings / 447 observations; LOC 0 blocking (one pre-existing Work Plane warning); conventions and scope green |
| DOCS | **PASS** | ADR-0009, `DISTRIBUTION-LIFECYCLE.md`, `UPDATING.md`, both READMEs |
| NON-VACUITY | **PASS** | 34/34 guards proved necessary |
| EXTERNAL REVIEW | **CLOSED — P0 = 0, P1 = 0** | bounded Round 8 plus focused Round 9, §11 |

### Test totals

```
tests/test_lifecycle_matrix.py         27
tests/test_lifecycle_ownership.py      23
tests/test_lifecycle_security.py       35
tests/test_lifecycle_transactions.py   39
tests/test_lifecycle_update.py         31
tests/test_lifecycle_cli.py            20
                                       ---
                                      175   all green
```

### Transition matrix

| Initial | Operation | Expected | Result |
|---|---|---|---|
| none | init Standard | Standard | PASS |
| none | init Verified | Verified | PASS |
| Standard | init Standard | no-op | PASS |
| Verified | init Verified | no-op | PASS |
| Standard | switch Verified | Verified | PASS |
| Verified | switch Standard | Standard + dormant Verified | PASS |
| Standard | uninstall | active stack removed, data preserved | PASS |
| Verified | uninstall | active stack removed, audit data preserved | PASS |
| Standard | uninstall --purge | clean | PASS |
| Verified | uninstall --purge | clean | PASS |
| uninstalled | reinstall Standard | Standard | PASS |
| uninstalled | reinstall Verified | Verified | PASS |
| Standard | update | updated Standard | PASS |
| Verified | update | updated Verified, history intact | PASS |
| updated | rollback | previous state | PASS |
| interrupted | repair | valid state | PASS |

### Cross-platform matrix (CI run `33921500321`, exact SHA `38ccd2f`)

| Job | ubuntu | windows | macos |
|---|---|---|---|
| Distribution lifecycle, py3.11 | PASS | PASS | PASS |
| Distribution lifecycle, py3.13 | PASS | PASS | PASS |
| Clean install E2E | PASS | PASS | PASS |
| Installers | PASS | PASS | PASS |
| Hooks | PASS | PASS | PASS |
| Verified Work Plane V2 | PASS | PASS | — (unchanged scope) |

### Automatic update detection behaviour

| Situation | Behaviour | Test |
|---|---|---|
| newer release | notification, no action | `test_a_newer_release_is_reported_as_available` |
| same version | no notification | `test_the_same_version_produces_no_notification` |
| offline | `OFFLINE`, not fatal | `test_an_unreachable_source_is_offline_not_a_crash` |
| cached result | no network | `test_status_reads_the_cache_and_never_the_network` |
| auto-check disabled | no network | `test_disabling_auto_check_in_preferences_stops_it_too` |
| `AINATIVE_NO_UPDATE_CHECK=1` | no network | `test_the_disable_variable_stops_every_network_check` |
| verify / converge / trust / work | no network call at all | `test_a_verified_command_never_triggers_an_update_check` |

### Non-vacuity — 34/34

Each guard is reverted in a scratch copy and its test must then fail
(`python scripts/lifecycle_non_vacuity.py`).

```
The full named list is maintained by `scripts/lifecycle_non_vacuity.py`; all 34
cases passed, including `lock_claim_identity` and
`lock_release_is_serialized`.
```

Five cases were reported **VACUOUS** on their first run and every one was
informative: three guards were layered, so removing a single layer proved
nothing (`archive_traversal`, `profile_preservation`, `journal_id_containment`
— the last needing all three of its layers removed), and one test could not
observe commit ordering at all and had to be rewritten to model a kill rather
than an exception.

---

## 8. Dogfood — the feature judged by the stack it installs

A real Work Contract for Distribution & Lifecycle v1: eight requirements, one
per invariant ADR-0009 fixes, each with an acceptance criterion and a
verification specification whose command is the suite that decides it. Run
through `evaluate_work()` — the production boundary — in a throwaway governed
clone.

```
verdict          CONVERGED
source_commit    38ccd2f60e24fe895743966db092438b2a0723a2
requirements     8       verifications  8 PASS      gaps  0
```

Record: `docs/qualification/lifecycle-v1-dogfood.json`.
Instrument: `scripts/lifecycle_dogfood.py`.

**What this is not.** The record carries
`trust_provenance: agent_bootstrapped_in_a_throwaway_clone` and
`authority_claim: none - dogfood evidence only`. ADR-0006 states the runtime
cannot distinguish a trusted operator from a controlled agent performing the
bootstrap ceremony, and the same process that wrote this work bootstrapped the
trust it is judged under. It is evidence that the declared properties were
checked. It is not evidence that a human authorised them.

**The first run was `NOT_CONVERGED`, correctly.** The non-vacuity command emits
its own structured record and the contract declared a `unittest` substance
adapter that cannot read it, so the plane reported `SUSPICIOUS_VERIFICATION` on
a run that had passed. The command now reports how many guards it proved and
the contract declares that count as the minimum, so adding a guard without
widening the contract is a refusal rather than a quiet pass.

Standard does not depend on any of this: the product installs and runs without
the Work Plane.

---

## 9. Empirical findings

The numbering reaches EMP-LC-042; IDs 004 and 005 were never assigned, leaving
40 accepted defects. Each has a reproducer, fix and regression unless explicitly
listed as rejected below. Severity is my own assessment, stated even where it
differs from the reporter's.

| ID | Sev | Defect | Found by | Guard |
|---|---|---|---|---|
| EMP-LC-001 | P2 | a declared data root with no content yet was reported `MISSING`, so a healthy fresh Verified install exited non-zero | smoke | — |
| EMP-LC-002 | P2 | an uninstall plan reported a managed *region* removal as a file removal, telling users their `.gitignore` would be deleted | smoke | — |
| EMP-LC-003 | P2 | `apply`/`remove` on an external block were not exact inverses; an uninstall left a stray blank line | smoke | `external_block_scope` |
| EMP-LC-006 | P1 | a transaction backed up with `copy2`, so `--purge` on a data root raised `PermissionError` and left the deletion unrecoverable | suite | — |
| EMP-LC-007 | **P0** | legacy adoption recorded a customised file at its on-disk digest, which made it compare `UNCHANGED` and let the very next install overwrite it | suite | `legacy_adoption` |
| EMP-LC-008 | P2 | `--force-unlock` retried without removing the lock, failing on the second `O_EXCL` exactly as on the first | suite | — |
| EMP-LC-009 | P1 | a prompt on a stdin claiming to be a terminal and then returning EOF raised a traceback and exit 1 instead of the documented refusal | suite | — |
| EMP-LC-010 | **P0** | purging a project holding transaction backups told the applier to back up the backup directory into itself, recursing until the interpreter gave up | clean-install E2E | — |
| EMP-LC-011 | P2 | the suite compared paths against `mkdtemp`'s answer while the CLI resolves; different strings on macOS (`/private/var`) and Windows CI (`RUNNER~1`) — test-only | CI | — |
| EMP-LC-012 | P1 | pruning removed the file and kept its state record, so a routine update left `doctor` reporting `MISSING` permanently and `repair` unable to clear it | self-review | `ownership_prune` |
| EMP-LC-013 | P1 | the no-op branch of `install` still committed the active profile, and did so without the lock | self-review | — |
| EMP-LC-014 | P1 | `update rollback` restored what the update replaced and left what it created, with a state matching neither | self-review | `rollback_completeness` |
| EMP-LC-015 | P2 | tree components were excluded from the case-fold collision check, in the guard that exists for exactly that case | external | — |
| EMP-LC-016 | P1 | `profile purge verified` was the only mutation with no interrupted-transaction gate, so the most destructive command could run on an unrecovered project | external | `purge_recovery_gate` |
| EMP-LC-017 | P2 | rollback metadata was a second record written after the commit, so a crash between them left an update applied and unreversible | external | — |
| EMP-LC-018 | **P0** | `--purge` deleted a managed file the user had edited — silently, and against the retention table, which promises it is kept | external | `purge_respects_user_edits` |
| EMP-LC-019 | P1 | a tampered transaction journal's `id` became a filename, so `../../../../escaped` made `repair` write outside the project root | external | `journal_id_containment` |
| EMP-LC-020 | P2 | the purge emptied `.ai-native/lifecycle/` with `rmtree`, taking anything a user had put there | external | — |
| EMP-LC-021 | **P0** | the orphan-removal sibling of EMP-LC-018 could delete a user-edited managed file | sibling review | `orphan_respects_user_edits` |
| EMP-LC-022 | P2 | purge still emptied nested journal directories with `rmtree` | sibling review | — |
| EMP-LC-023 | P2 | an adopted external region was recorded as not written by the stack | review | — |
| EMP-LC-024 | P1 | update dry-run wrote conflict files and update cache state | review | `dry_run_update_writes_nothing` |
| EMP-LC-025 | P1 | text-mode newline translation rewrote CRLF external configuration | CI/review | `crlf_preservation` |
| EMP-LC-026 | P2 | a marker quoted in prose opened a managed region | review | — |
| EMP-LC-027 | P2 | an invalid stored check interval crashed update status | review | — |
| EMP-LC-028 | P2 | a marker quoted inside a block closed it early | review | — |
| EMP-LC-029 | P1 | a string `"false"` became true and authorized deletion | review | `ownership_flag_typing` |
| EMP-LC-030 | P1 | `O_EXCL` exposed an empty lock before its payload was written | review | `lock_atomicity` |
| EMP-LC-031 | P1 | a killed transaction persisted no completed changes to recover | review | `journal_durability` |
| EMP-LC-032 | P1 | undo overwrote a file edited after interruption | review | `undo_respects_a_later_edit` |
| EMP-LC-033 | P2 | managed markers were not anchored to the end of their line | review | `marker_is_a_whole_line` |
| EMP-LC-034 | P1 | a write that raised after landing escaped rollback | review | `rollback_follows_the_journal` |
| EMP-LC-035 | P2 | `.new` files survived a failed update | review | `conflict_file_after_apply` |
| EMP-LC-036 | P1 | an old owner released a force-replacement owner's lock | review | `lock_release_is_owned` |
| EMP-LC-037 | P1 | update staging overwrote an existing user-owned `.new` file | review | `new_file_never_overwritten` |
| EMP-LC-038 | P1 | undo trusted a completed record outside the PREPARED plan | review | `undo_bounded_by_the_plan` |
| EMP-LC-039 | P2 | refused force-unlock escaped as a raw `OSError` | review | `force_unlock_reports_refusals` |
| EMP-LC-040 | P2 | repair rewrote state without retaining its previous record | review | `repair_archives_the_state` |
| EMP-LC-041 | P1 | timestamp-based metadata was not unique per lock acquisition | Windows CI | `lock_claim_identity` |
| EMP-LC-042 | P1 | claim comparison and unlink were separated by a force-replacement TOCTOU window | focused review | `lock_release_is_serialized` |

```
P0 open: 0        P1 open: 0        P2 open: 0
```

Every accepted finding above is fixed. EMP-LC-043 is FALSE: dot, parent,
Windows case-variant and real directory-link aliases resolve to the same
per-project mutation guard. Two proposed journal/marker arrangements were also
rejected with executable or source evidence, as recorded in the handoff.

---

## 10. Behaviour changes

1. **`install.py` no longer prunes a file it did not write.** `copy_tree`
   deleted anything under a managed directory the source no longer had —
   correct for a file the stack wrote, wrong for one the user edited, and it
   had no way to tell. Pruning is now decided per file by the recorded digest.
   The old flags (`--project-root`, `--skip-gstack`, `--with-gstack`,
   `--gstack-ref`, `--dry-run`) still work.
2. **The console entry point moved** from `ainative_workplane.cli:main` to
   `ainative.cli:main`, which dispatches. Every Verified command keeps its
   grammar, its output and its exit codes.
3. **The distribution is now `ainative-dev-stack`** and ships both packages.
4. **`.ai-native/lifecycle/` is new**, and is git-ignored where appropriate by
   the managed `.gitignore` region.

Existing users keep their stack, AI docs, skills, hooks, vault and Verified
Work Plane. A pre-lifecycle install is adopted, not migrated destructively.

---

## 11. Independent review

**Reviewer.** OpenAI Codex (`gpt-5.6-luna`) via `codex exec`, given an
independent context: the invariants, the severity definitions, a requirement
that every finding carry a reproducer or a `file:line` citation, and an explicit
instruction not to redesign the product. OpenCode was tried first and stopped on
a provider token limit before producing findings.

**Rounds and dispositions.** The bounded review sequence closed EMP-LC-015
through EMP-LC-042. Every accepted finding was reproduced before modification;
two proposed findings were rejected with evidence rather than repaired by
assumption. Round 8 on `38ccd2f` returned no new P0/P1. Round 9 then reviewed
only claim identity, mutation guard, force replacement, dead-owner reclaim,
release and equivalent project paths; it returned no reproducible P0/P1.

| Reported | Verdict | Disposition |
|---|---|---|
| `--purge` deletes a user-edited managed file | **TRUE** (I rate it P0, above the reported P1) | fixed — EMP-LC-018 |
| tampered journal id escapes the project root | **TRUE** (P1) | fixed — EMP-LC-019 |
| `profile purge` bypasses the recovery gate | **TRUE** (P1) | fixed — EMP-LC-016 |
| `--purge` rmtree removes a user file under `lifecycle/` | **TRUE** (P2, reported P1) | fixed — EMP-LC-020 |
| tree components skip the collision check | **TRUE** (P2, reported P1) | fixed — EMP-LC-015 |
| rollback metadata written after the commit | **TRUE** (P2, reported P1) | fixed — EMP-LC-017 |

The complete dispositions are in the EMP table and handoff. Severity was never
raised on a theoretical escalation path; destructive classifications required
an executable sequence.

**Final independent evidence.** The final reviewer inspected exact SHA
`38ccd2f60e24fe895743966db092438b2a0723a2` and independently verified GitHub
run `33921500321` as successful. It reported P0 = 0, P1 = 0, and two P2 closure
items: update the lock architecture prose and test equivalent project paths.
Both are included in the packet-finalization commit. The alias test closed
EMP-LC-043 as FALSE rather than promoting it theoretically.

**External review is closed.** The bounded zero-P0/P1 round and its focused
confirmation both satisfy the convergence rule. This is a release gate result,
not a claim of universal correctness.

---

## 12. Known limitations

Stated because they are true, not because they were discovered late.

1. **Release-source compromise is not covered.** SHA-256 over the archive
   proves the bytes match what the source described. An attacker controlling
   the source controls both the archive and the digest. Release signing is not
   implemented and is not claimed.
2. **Rollback scope is the project.** `update rollback` reverses the update
   transaction while it is retained (the last 5). It cannot restore a Python
   package installed elsewhere on the machine.
3. **Bootstrap trust remains a privileged human act.** `init --profile
   verified` prepares the environment and reports that the bootstrap is still
   required. It does not perform it. Bootstrap trust *before* a controlled
   agent has repository access — ADR-0006, unchanged.
4. **`--purge` retains a conflict's `.new` files.** They hold the upstream
   content you have not merged yet, so they are yours to compare and delete.
5. **The lifecycle CLI requires Python 3.11+.** The AI-docs tooling it installs
   still runs on 3.8+. Three surfaces, three statements, in
   `docs/DISTRIBUTION-LIFECYCLE.md` §14.
6. **`updater.apply` does not hold the lock across the download.** The mutation
   inside it does, so two concurrent updates serialise at the transaction and
   one gets `LOCK_HELD`; the transaction guarantees are unaffected.
7. **A symlinked managed path fails the operation closed.** If a managed
   destination is a symlink the stack did not create, the plan refuses with
   `PATH_ESCAPE` rather than writing through it. Safe, and deliberately not
   silent.
8. **The manifests are trusted because they ship inside the package.** An
   attacker who can edit `ainative/lifecycle/data/*.json` already has code
   execution. They are still validated at load, so a corrupted file is a
   refusal rather than a surprise.
9. **The `.new` conflict files are not tracked in the install state**, so an
   uninstall leaves them.

---

## 13. Regression status of the Verified Work Plane

No file under `ainative_workplane/` was modified on this branch. The full V2
suite (187 tests: contracts, controller, snapshot, runner, convergence,
substance, authorization, traceability, convergence history, CLI, integrations,
pilot, harness matrix, historical case, adversarial A01–A53, authority A54–A70,
authority origin) runs green locally and in CI on Linux and Windows. The
qualification recorded on `spec` is not regressed.

---

## 14. Verdict

```
PRODUCTION  = PENDING EXACT CI
MERGE-READY = PENDING EXACT CI
```

```
P0 = 0
P1 = 0
Standard usable independently          YES
Verified extends Standard correctly    YES
Standard <-> Verified reversible       YES, non-destructively, both ways
uninstall safe                         YES
purge explicit                         YES, and scoped to declared data roots
updates detectable                     YES, cached, never applied automatically
updates transactional                  YES, with a complete reversal
user changes preserved                 YES, through every operation
Verified history preserved             YES, byte for byte across the round trip
legacy users migratable                YES, conservatively
Windows / Linux / macOS tested         YES, 3 OS x 2 Pythons
Work Plane qualification not regressed YES
clean install works                    YES, from a wheel with no checkout
external reviewer                      P0 = 0, P1 = 0
external review                        CLOSED after bounded Round 8 + focused Round 9
```

**Merge recommendation.** Merge `feat/distribution-lifecycle-v1` into `spec`
after the packet-finalization SHA receives an exact green CI run, squashed. Not
merged by this work: the mandate withheld that authority, and it should stay
withheld until a human has read §11 and §12.
