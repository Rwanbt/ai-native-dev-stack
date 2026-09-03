# Review Packet — Authority Hardening, Round 5

Answers the review of `2f0420b`: two P0, three P1. Four are addressed; the
fifth (reusable attested evidence) is unchanged and still open by design.
Nothing here is self-certified.

## Revision

```text
reviewed        2f0420b
this packet     see the CI section
branch          spec
pull request    #16
```

## All four reproduced first, against `2f0420b`

| Finding | Reproduction |
| --- | --- |
| A97 self-authored initial contract | A sibling work created under the project's **legitimate pinned root**, with a requirement the actor wrote (`"nothing in particular"`), a specification the actor wrote, and a registry command pointing at a script the actor wrote that prints `OK`. Verdict `CONVERGED`. |
| A98 unauthorized signer | A second SSH identity added to the repository's allowed-signers file. The actor signs its own mutation approval with it. Git reports `%GS intruder@example.invalid`. Mutation accepted, revision 2. |
| A99 mixed path set | `src/unsigned.py` committed unsigned, then `src/signed.py` committed signed. `observe(repo, [both]).signature_verified` → `True`. |
| A100 predecessor-less root | The current root's content changed with no `predecessor` and no `transition_approval`. Verdict `CONVERGED`. |

The reviewer's reading was right in every case. Two are the boundary of a
round-4 fix rather than something it missed: project trust authenticated the
*root* a work used but not the *contract* that work claimed to be judged by,
and `signature` proved Git accepted a signature without asking whose.

## Corrections

| Finding | Correction | Case |
| --- | --- | --- |
| P0-A initial contract self-authoring | `work_creation_approval` at the fixed path `<work>/creation_approval.json`, binding the anchor (`trust_uid` + `trust_digest`), the exact `genesis_digest`, and the anchor's predicate. The controller refuses to write an unadmitted work; the evaluator refuses to converge on one, **recomputing** the genesis digest from `revisions/1/` rather than reading a field. | A97 |
| P0-B signer authorization | The anchor pins `authorized_signers` by key fingerprint (`%GF`, falling back to `%GK` — the same field for GPG and SSH). `signature_verified` requires the signer to be in that set; `authorized_signers=None` establishes nothing rather than accepting any valid signature. | A98 |
| P1-A conjunctive provenance | `signature_signers()` resolves the identity **per path**, one `git log -1` each. A path whose last commit is unsigned contributes `None`, so a set verifies only when every member does. | A99 |
| P1-B root chain connectivity | Two points: the controller refuses a root whose commitment changed unless it names the committed root as predecessor and carries a transition approval; `_valid_root_chain` terminates at a predecessor-less root only when it *is* the anchor's pinned genesis. | A100 |
| P1-C reusable attested evidence | Unchanged and still open: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT`. | ADR-0003 §1 |

Decisions and rejected alternatives: [ADR-0005](adr/0005-initial-contract-admission-and-signer-authorization.md).

## The fix that needed a fix, reported because it is the interesting part

Pinning the signers in the anchor is **circular on its own**. An actor that
rewrites the anchor to add its own fingerprint is then measured against the
list it just wrote — and that is not a hypothesis. It is what
`test_a98_an_anchor_rewritten_to_authorize_the_actor_establishes_nothing`
caught in this round's own correction, on the first run.

The cut: **the anchor must have exactly one commit in its history.** A file
with a single commit still says what its author said. This also turns
ADR-0004's "a governed project never re-bootstraps silently" from an API
refusal into a structural property — `bootstrap()` refusing to overwrite never
stopped a direct write to the path.

*Cost, stated:* changing a governed project's authorized signers, including
after a lost key, is not an edit. It requires establishing a new anchor.

## The new cases are not vacuous — checked, not asserted

The four fixes were reverted in place and the cases re-run. Eleven blocking
cases failed; every control kept passing:

```text
FAIL  A97   an initial contract nobody admitted is refused
FAIL  A97   an actor cannot admit its own initial contract
FAIL  A97   an admission for another contract admits nothing
FAIL  A97   a work whose admission disappears stops being authoritative
FAIL  A98   a valid signature by an unauthorized signer is refused
FAIL  A98   widening the verifier configuration grants no authority
FAIL  A98   an anchor rewritten to authorize the actor establishes nothing
FAIL  A99   one signed commit does not sign a whole path set
FAIL  A100  a root change without a predecessor is refused
FAIL  A100  a predecessor that is not the committed root is refused
FAIL  A100  a predecessor-less root is not a second genesis
```

Controls that stayed green: the properly admitted contract still creates and
converges; the authorized signer's mutation is still accepted; a fully signed
path set still verifies; a proper rotation still commits and converges.

## Where the new cases live

```text
tests/test_workplane_authority_origin.py
  InitialContractAdmissionTests   A97   (5 cases)
  SignerAuthorizationTests        A98   (4 cases)
  MultiPathSignatureTests         A99   (3 cases)
  RootConnectivityTests           A100  (4 cases)
```

A97, A98 and A99 are skipped where `ssh-keygen` is absent; they execute on both
CI legs. A100 needs no signing and runs everywhere.

## What changed in the engine

```text
bootstrap.py    authorized_signers; admits(); read_creation_approval();
                anchor must have exactly one commit
provenance.py   signature per path, not per path set; signer identity;
                authorized_signers required; commit_count()
controller.py   creation approval on create; root predecessor connectivity;
                genesis_normative_digest() recomputed from revision 1
evaluator.py    WORK_NOT_ADMITTED; anchor resolved once and threaded;
                genesis digest passed into the chain walk
trust.py        the chain terminates at the pinned genesis
contracts.py    work_creation_approval schema; authorized_signers
cli.py          trust bootstrap --signer
```

## A round-4 residual risk that is now closed

The round-4 packet said: *"The project trust anchor is a file. `bootstrap()`
refuses to replace one, but nothing stops a direct write to the path."* The
one-commit rule closes that. Under `signature` a rewritten anchor establishes
nothing; under `recorded_owner_ack` it still establishes what that predicate
was always worth.

## Residual risks, restated

- Under `recorded_owner_ack`, at every level — mutation approval, creation
  approval, project anchor — an actor with commit rights is the whole bar. Only
  `signature` with a pinned signer set excludes it.
- `git_reviewed` and `ci_verified` still have no provider; a policy requiring
  either fails closed.
- A project that loses its signing key cannot rotate signers without
  establishing a new anchor. Deliberate, and a real operational cost.
- Resolving signing identity costs one `git log` per observed path. A very
  large declared scope makes an observation proportionally slower.
- Authority drift is still compared before and after the runs, not
  continuously.
- Convergence still re-executes every declared verification.
- `scripts/workplane_pilot.py` still calls the pure `converge()` kernel rather
  than `evaluate_work`, so it exercises none of this. It is labelled
  `authority: smoke_pilot_only`.

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

Five reviews, five sets of findings, three of them inside a correction — and
this round's own fix contained one, caught by its own test rather than by the
next reviewer. That is the argument for keeping `P0 = 0` unclaimed until
someone other than the author says it.
