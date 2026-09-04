# Review Packet — Authority Hardening, Round 7

Answers the review of `386b326`: **P0 = 0**, P1 = 3, P2 = 2. All three P1s are
addressed — two corrected, one unchanged by design — and both P2s are decided
rather than left ambiguous. Nothing here is self-certified.

## Revision

```text
reviewed        386b326
this packet     fa01c41
branch          spec
pull request    #16
```

## CI

```text
run 33806949592   every job green
                  Verified Work Plane V2 on ubuntu-latest and windows-latest
```

Local: 148 V2 tests OK (2 platform skips), plus 38 `ai_docs`, 40 `scripts` and
7 `hooks` tests, the three deterministic scripts, and the scope and convention
gates.

## All three reproduced first, against `386b326`

| Finding | Reproduction |
| --- | --- |
| P1-A policy/root atomicity | A policy-only mutation committed cleanly at revision 2. `policy_commitment(project_policy)` = `fcb0eab2…`, `approval_root.policy_digest` = `94ca7396…`. The verdict is no longer `CONVERGED`, which is the point: the writer produced a state that can never be authority and left the evaluator to notice. |
| P1-B historical facts | `_valid_root_chain` passes one `facts` object — a single observation of the *current* authority artifacts — into every `_authorized_transition` call. Reproduced by construction: nothing binds a transition to its own evidence. |
| P2 approval replay | Revision 1 approves a weak registry; a stricter registry is committed at revision 3; replaying the revision-1 approval reaches revision 4 with the weak one back. |

## Corrections

| Finding | Correction | Case |
| --- | --- | --- |
| P1-A | A root must carry the commitment of the policy it is written with, checked before the revision is committed. Atomicity follows by composition: a new policy commitment changes the root's own commitment, and a changed root already requires a predecessor and a transition approval. | A104 |
| P1-B | The manifest — the commit marker — records, per rotation, the commit that carried the approval and that approval's digest. The evaluator re-establishes each transition's facts from that commit with `observe_commit()`. A transition absent from the bound mapping is **invalid**: no evidence is not a pass. | A105 |
| P2 replay | `mutation_approval` binds `base_digest` as well as `target_digest`, so it authorizes one transition rather than one destination. | A106 |
| P1-C reusable evidence | Unchanged and still open: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT`. | ADR-0003 §1 |

Decisions and rejected alternatives: [ADR-0007](adr/0007-transition-evidence-and-approval-scope.md).

## Two things I got wrong inside this round, reported because they are the useful part

**The atomicity fix had an unreachable branch.** My first draft added a
separate *"a policy change must rotate the approval root"* check after the
policy-commitment check. It can never fire: a root carrying the new policy
commitment necessarily has a different root commitment from the old one, so the
earlier check has already refused. It was dead reassurance and it is removed.
One rule does the work, and the ADR says so.

**The first A106 case proved nothing.** Its intermediate "strengthening"
returned to *exactly* the revision-1 state — so the replay was legitimate:
identical state, genuinely approved transition. The case had to be rebuilt with
a distinct third state (a different timeout) before it demonstrated anything.
The reproduction in this packet uses the rebuilt version.

## The P2 decisions, stated

The review asked for these to be explicit rather than ambiguous.

- **`mutation_approval` is transition-scoped** (option B). It names the state
  left and the state reached. This is what closes the replay.
- **`work_creation_approval` is content-addressed** (option A). Genesis has no
  base to name, and two works with byte-identical contracts are the same
  contract at the same bar. The same admission may therefore create more than
  one such work. If one-shot admission is ever needed, the binding to add is a
  pre-created work identity — written down in ADR-0007 §3 rather than left to
  be rediscovered.
- **The one-commit anchor rule depends on trustworthy Git history**, which the
  threat model already places outside V2's scope. No overclaim is made about
  history rewrite; the sentence stays visible in `docs/THREAT_MODEL.md`.

## The new cases are not vacuous — checked, not asserted

The three fixes were reverted in place and the cases re-run:

```text
FAIL  A104  a policy-only mutation is refused
FAIL  A104  a root that commits to another policy is refused
FAIL  A104  a root committing to an unrelated policy is refused
FAIL  A105  current authority cannot supply historical facts
FAIL  A106  an old approval cannot undo a later strengthening
```

Controls that stayed green: policy and root moving together is accepted and
converges; the commit marker records what authorized each transition; a
committed rotation still converges; an approval issued against the current
state is accepted.

## Where the new cases live

```text
tests/test_workplane_authority_origin.py
  PolicyRootAtomicityTests           A104  (4 cases)
  HistoricalTransitionEvidenceTests  A105  (3 cases)
  ApprovalReplayTests                A106  (2 cases)
```

## What changed in the engine

```text
provenance.py    observe_commit(), recording_commit()
controller.py    _require_policy_root_atomicity(); _transition_authority()
                 recorded into the manifest root_chain entry; _committed_pairs()
trust.py         transition_facts keyed by successor UID; an unbound transition
                 is invalid
evaluator.py     _transition_facts() re-establishes each transition from its
                 own commit
contracts.py     root_chain[].authority; mutation_approval.base_digest
authorization.py base_digest checked
```

## Residual risks

- **Genesis is not verifiable by the runtime** (ADR-0006). Unchanged.
- A historical transition's facts are re-established from an immutable commit,
  but against the signer set the anchor pins **today**. Removing a signer
  invalidates that identity's earlier transitions. Fail-closed, and locally the
  honest reading: the project no longer trusts them.
- A creation approval may admit more than one work with identical contracts —
  decided, see above.
- `git_reviewed` and `ci_verified` still have no provider.
- Rotating authorized signers requires a new anchor.
- Authority drift is compared before and after the runs, not continuously.
- Convergence re-executes every declared verification.
- `scripts/workplane_pilot.py` calls the pure `converge()` kernel, not
  `evaluate_work`; labelled `authority: smoke_pilot_only`.
- The one-commit anchor rule assumes trustworthy Git history.

## Still open

```text
HISTORICAL   no blind case run
PILOT        no two-harness pilot run
```

## Verdict

```text
P0 = not self-certified
P1 authority = not self-certified
PRODUCTION = NO-GO
MERGE spec -> main = NO-GO
```

The previous review reported `P0 = 0`. That is its finding, not mine, and this
packet does not restate it as a claim. What I can say is narrower: the three
findings it raised are reproduced, corrected, and held by cases that fail when
the corrections are removed.
