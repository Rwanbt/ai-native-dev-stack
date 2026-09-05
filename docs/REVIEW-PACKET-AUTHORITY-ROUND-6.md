# Review Packet — Authority Hardening, Round 6

> **STATUS: HISTORICAL QUALIFICATION RECORD** — retained for auditability.
> This document records the state of the Verified Work Plane work at the time
> it was written; it is not the current operational status. See
> [docs/VERIFIED-WORK-PLANE.md](VERIFIED-WORK-PLANE.md) for current state.

Answers the review of `92875e5`: one P0, three P1. The P0 is **declared, not
fixed** — deliberately, and the reasoning is below. Two P1s are corrected; the
third is unchanged and open by design.

## Revision

```text
reviewed        92875e5
this packet     386b326
branch          spec
pull request    #16
```

## CI

```text
run 33801342143   every job green
                  Verified Work Plane V2 on ubuntu-latest and windows-latest
```

Local: 139 V2 tests OK (2 platform skips), plus 38 `ai_docs`, 40 `scripts` and
7 `hooks` tests, the three deterministic scripts, and the scope and convention
gates. `docs/qualification/claude-code.json` regenerated at this commit —
still the author's own harness, still not independence.

## All three reproduced first, against `92875e5`

| Finding | Reproduction |
| --- | --- |
| P0 self-bootstrapping genesis | The test fixture **is** the attack protocol. One actor generates the signing key, configures Git to verify it, names its own fingerprint in `authorized_signers`, signs the anchor, signs the creation approval, and converges. `anchor_refusal` → `None`. Verdict `CONVERGED`. |
| P1 policy evolution | The controller refuses an evolved policy outright: the root must change with the policy, and a root change demands a predecessor. Beneath that, `_valid_root_chain` required **every** root in the walk to carry the *current* policy commitment, so an evolved project could never validate its own genesis. |
| P1 controller anchor | The anchor rewritten to add an intruder fingerprint: `anchor_refusal` returns *"not recorded exactly once (2 commits touch it)"* — and `WorkController.mutate` still wrote revision 2 under it. |

## The P0: declared, not fixed

The review offered two directions and recommended the first. **Option A is
taken.**

A root of trust cannot prove its own legitimacy from data whose authority comes
from that root. Round 5's one-commit rule proves the anchor was not *edited*
afterwards; it cannot prove anyone outside the actor chose it. Adding
`bootstrap_authorized_by`, an `owner` field, or a bootstrap signature inside the
same file moves the circle rather than cutting it — which is exactly what the
review said not to do.

So the boundary is stated:

```text
Verified Work Plane guarantees begin AFTER a trusted operator has
established the project trust anchor. Establishing it is a privileged
operation inside the trusted computing base, and its legitimacy is an
assumption the runtime cannot verify.

Deployment requirement: trusted bootstrap MUST precede controlled-agent access.
```

What changed concretely:

- `ainative trust bootstrap` is documented as privileged in its own `--help`,
  and its output now carries `"authority": "privileged_trust_establishment"`;
- ARCHITECTURE.md carries the boundary as a blockquote rather than an implied
  guarantee, and the threat model has a dedicated table for it;
- **the overstated claim is corrected.** "Under `signature` an actor without the
  key cannot produce a valid anchor" is true only *after* a trusted anchor
  exists. Before that, the actor makes the key. That sentence was in the round-4
  and round-5 material and was wrong at the boundary;
- `initialized_by` is documented as caller-supplied metadata that nothing
  verifies.

**Option B — an external machine-verifiable root** (OS-level policy, an
organizational trust configuration, remote attestation) is the only thing that
would protect genesis against an actor present *before* bootstrap. It needs a
trust source this product does not have. It is not built, and ADR-0006 records
why rather than leaving it implied.

A101 asserts the **boundary**, not a defence: the self-bootstrapped project
converges, and the runtime makes no claim about who performed genesis. If an
external trust source is ever added, that case must fail and be rewritten.
That is its purpose.

## Corrections

| Finding | Correction | Case |
| --- | --- | --- |
| P1 policy evolution | The manifest records a committed **policy chain** beside the root chain. Only the current root must carry the current policy commitment; every earlier root must carry one the project committed; and a transition into root *R* is judged under **R's predecessor's** policy — its predicate and its required facts. | A102 |
| P1 controller anchor | One `bootstrap.verified_anchor()`, called by `WorkController` before it writes and by `evaluate_work` before it decides, so the two cannot drift. An invalid anchor now refuses the write (`UNGOVERNED_PROJECT`) instead of producing a revision the evaluator declines to judge. | A103 |
| P1 reusable attested evidence | Unchanged and still open: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT`. | ADR-0003 §1 |

Decisions and rejected alternatives: [ADR-0006](adr/0006-bootstrap-trust-boundary-and-policy-evolution.md).

## A consequence of the policy fix worth disagreeing with

Because the current root must carry the current policy commitment, **changing
the policy rotates the root in the same mutation.** That is not a workaround: a
root of trust names the policy it was established under, so a policy change is
a new root generation, and the transition approval issued under the
predecessor's policy is precisely the authorization for both.

It does mean policy authoring is heavier than artifact authoring. If a reviewer
thinks that coupling is wrong, this is the place to say so — the alternative is
to let a root outlive the policy that established it, and I could not find a
version of that which preserves `P0 authorized P1`.

## The new cases are not vacuous — checked, not asserted

The two P1 fixes were reverted in place and the cases re-run:

```text
FAIL  A102  an authorized policy change still converges
FAIL  A102  a later weaker policy does not authorize an old transition
FAIL  A103  an invalid anchor cannot authorize a write
FAIL  A103  an invalid anchor cannot admit a new work
```

Controls that stayed green: a policy never committed authorizes nothing, and a
valid anchor still authorizes writes.

A101 is deliberately not in that list — it asserts a limitation, and reverting
a fix that does not exist changes nothing about it.

## Where the new cases live

```text
tests/test_workplane_authority_origin.py
  BootstrapTrustBoundaryTests       A101  (2 cases — the boundary, not a defence)
  PolicyEvolutionTests              A102  (3 cases)
  ControllerAnchorVerificationTests A103  (3 cases)
```

## What changed in the engine

```text
bootstrap.py    verified_anchor(): locate, load and verify in one place
controller.py   project_anchor() verifies; committed policy chain in the
                manifest; policy_history(); one _committed_chain() for both
trust.py        each root resolves its own policy; a transition is judged under
                the predecessor's; policy_chain threaded through evaluate_trust
evaluator.py    policy_history passed into trust; anchor verified once
contracts.py    manifest policy_chain
cli.py          trust bootstrap labelled privileged in help and in output
```

## Residual risks

- **Genesis is not verifiable by the runtime.** Stated above; the mitigation is
  a deployment requirement, not a mechanism.
- A historical transition is judged under its predecessor's *policy* but against
  facts observed **now**. A local checkout has no record of what was observable
  at the time.
- Under `recorded_owner_ack`, at every level, an actor with commit rights is the
  whole bar — and only after genesis does `signature` change that.
- `git_reviewed` and `ci_verified` still have no provider.
- Rotating authorized signers, including after a lost key, requires a new
  anchor.
- Authority drift is compared before and after the runs, not continuously.
- Convergence re-executes every declared verification.
- `scripts/workplane_pilot.py` calls the pure `converge()` kernel, not
  `evaluate_work`, and is labelled `authority: smoke_pilot_only`.

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

Six reviews, six sets of findings. This round's P0 was not a defect in the code
but a claim the documentation was making that the code could not support — and
the correction is to stop making it.
