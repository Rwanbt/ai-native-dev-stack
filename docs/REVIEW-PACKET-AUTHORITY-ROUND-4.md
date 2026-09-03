# Review Packet — Authority Hardening, Round 4

Answers the review of `2a6f838`: two P0, three P1. All five are addressed.
Nothing here is self-certified.

## Revision

```text
reviewed        2a6f838 (the review read the code, not only the round-3 packet)
this packet     2f0420b
branch          spec
pull request    #16
```

## CI

```text
run 33783785831   every job green
                  Verified Work Plane V2 on ubuntu-latest and windows-latest
```

The signature cases are not skipped on either leg: `ssh-keygen` is present on
both runners, so A94's satisfied-predicate control and A95's unsigned-anchor
case executed on Linux and on Windows. The only skips remain the two special-
file cases Windows cannot create, which the Linux leg runs.

Local: 115 V2 tests OK with those two skips, plus 38 `ai_docs`, 40 `scripts`
and 7 `hooks` tests, the three deterministic scripts, and the scope and
convention gates.

`docs/qualification/claude-code.json` records the four gates reproducing at
`2f0420b` — four gates, exit 0, `authority: qualification_evidence_only`.
**That is the author's own harness and is not independence.** The `opencode`
and `codex-desktop` qualifications in the same directory are at older commits
and would need re-running at this HEAD by those harnesses to mean anything
about it.

## Both P0 reproduced first, against `2a6f838`

| Finding | Reproduction |
| --- | --- |
| A self-recorded approval is treated as approval | The declared verification genuinely fails (`NOT_CONVERGED`). The actor writes a registry pointing the same command at a script that passes, builds the exact `mutation_approval` that state needs, writes it, commits it, and calls `mutate`. Accepted. Verdict `CONVERGED`. The policy's predicate was named `review`; its `required_mutation_facts` was `{"git_recorded": true}`. |
| Genesis authorizes itself | `GovernedWork` creates a work with its own policy, root, registry and specifications. No project-level trust artifact exists anywhere in the repository — checked, not assumed. Verdict `CONVERGED`. |

The P1 on `root_history()` was reproduced the same way: a crash injected
between promotion and the manifest replace leaves `revisions/2/` on disk, the
committed revision is still 1, and `root_history()` returned both roots.

The reviewer's reading was right in each case, including that the round-3
packet had already conceded the first one in its own residual-risk section.

## Corrections

| Finding | Correction | Case |
| --- | --- | --- |
| P0-A predicate was an identifier | `predicates.py` holds a closed table: `signature`→`signature_verified`, `git_review`→`git_reviewed`, `ci_attestation`→`ci_verified`, `recorded_owner_ack`→`git_recorded`. The requirement belongs to the mechanism; `required_mutation_facts` may add to it and never subtract. An unimplemented predicate is never satisfied. Applied to mutation approvals, waivers, human approvals and root transitions alike. | A94 |
| P0-B genesis was self-authorizing | `bootstrap.py` and `ainative trust bootstrap`. `.ai-native/trust/project_trust.json` pins the genesis approval root and names the predicate the anchor itself must satisfy. A work naming an unpinned root is refused `UNGOVERNED_GENESIS`; a work no anchor pins is `PROJECT_TRUST_UNINITIALIZED`, which is `INVALID`. Bootstrap refuses to replace an existing anchor. | A95 |
| P1-A no provider implemented any independent predicate | `provenance.signature_verified()` asks Git whether the commit that last wrote the *observed paths* verifies (`git log -1 --format=%G?` = `G`), against the configured keyring or allowed-signers file. `signature` is now the documented production default, replacing the `git_reviewed` claim in ARCHITECTURE.md. | A94 control, A95 signature case |
| P1-B history came from directory listing | The manifest — the commit marker — carries `root_chain`. A revision enters it through the atomic replace that makes it committed, and each historical root is re-digested when read. | A96 |
| P1-C reusable attested evidence | Unchanged and still open: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT`. | ADR-0003 §1 |

Decisions and rejected alternatives: [ADR-0004](adr/0004-project-trust-bootstrap-and-approval-predicates.md).

## The new cases are not vacuous — checked, not asserted

The three fixes were reverted in place and the file re-run. Every blocking
case failed; every control kept passing:

```text
FAIL  A94  a self-recorded approval does not satisfy an independent predicate
FAIL  A95  a work the project never pinned is unevaluable
FAIL  A95  a second work cannot bring a root of its own
FAIL  A95  an anchor the actor only recorded does not satisfy signature
FAIL  A95  an unreadable anchor never reads as absent
FAIL  A96  a root from an uncommitted revision is not history
FAIL  A96  a root swapped under a committed chain entry is dropped
```

The controls that stayed green matter as much: A94's *satisfied-predicate*
case still performed the same mutation and converged, and A95's sibling-work
case still created a second work under the pinned root. Without those, A94
would pass in a build where nothing works at all.

## Where the new cases live

```text
tests/test_workplane_authority_origin.py
  ApprovalPredicateTests      A94  (3 cases: refusal, satisfied control, closed table)
  GenesisTrustTests           A95  (6 cases: uninitialized, foreign root, permitted
                                    sibling, refused re-bootstrap, unsigned anchor,
                                    unreadable anchor)
  CommittedRootHistoryTests   A96  (3 cases: orphan revision, committed rotation,
                                    swapped historical root)
```

A94 and the signature anchor case are skipped where `ssh-keygen` is absent.
They execute on both CI legs.

## Commits

```text
d55b161  fix(workplane): make a predicate a mechanism, and trust a project before its work
2f0420b  docs: record the fourth round, and name the default that is actually implemented
```

The first is ~490 lines, over the 400-LOC budget. Splitting it along the two
P0s would require an intermediate commit whose tests do not pass, because the
test fixture crosses both; this branch has shipped red twice and will not do it
a third time to satisfy a line count.

## What changed in the engine

```text
new   ainative_workplane/predicates.py    the closed predicate table
new   ainative_workplane/bootstrap.py     the project trust anchor
      contracts.py       project_trust schema; manifest root_chain; trust UID prefix
      controller.py      _require_project_trust on create; root_chain on commit;
                         root_history reads the committed chain
      evaluator.py       _project_trust_gaps, four new unevaluable codes
      provenance.py      signature_verified over the observed paths, not HEAD
      authorization.py   predicate satisfaction, separate from artifact provenance
      trust.py           a root transition clears the same predicate
      cli.py             ainative trust bootstrap | show
```

## Consequences a reviewer should weigh

- **There is no longer a posture where an approval need not be recorded.**
  `required_mutation_facts: {}` still parses, but the weakest predicate imposes
  `git_recorded` regardless. One controller test had to start committing its
  approvals; that is the correction working, not a fixture inconvenience.
- **The anchor pins the genesis root, not the current one**, matched against
  the work's committed chain. Pinning the current root would make rotation
  impossible without a second genesis, which is the thing ADR-0004 prevents.
- **The anchor deliberately does not pin the policy.** Every change to it since
  bootstrap passed the mutation bar, which checks each step against the
  authority in force at the time — stricter than a frozen digest, and it does
  not make ordinary authoring require a re-bootstrap.

## Residual risks, restated because they are the honest answer

- Under `recorded_owner_ack`, at either level, an actor with commit rights is
  the whole bar. That posture is now **named** rather than disguised. It is not
  protection, and a project that wants protection runs `signature`.
- The project trust anchor is a file. `bootstrap()` refuses to replace one, but
  nothing stops a direct write to the path; under `recorded_owner_ack` the
  actor can then commit it. Under `signature` it cannot produce one that
  verifies.
- `git_reviewed` and `ci_verified` still have no provider. A policy requiring
  either fails closed.
- Authority drift is still compared before and after the runs, not
  continuously.
- Convergence still re-executes every declared verification.
- `scripts/workplane_pilot.py` calls the pure `converge()` kernel directly, not
  `evaluate_work`. It therefore exercises neither the trust anchor nor the
  mutation bar. It is labelled `authority: smoke_pilot_only`; the label is
  accurate, and the script is not evidence about authority.

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

Four reviews have now each found real findings in what the previous round's
green cases did not ask — twice inside a correction. That is the argument for
keeping `P0 = 0` unclaimed until someone other than the author says it.
