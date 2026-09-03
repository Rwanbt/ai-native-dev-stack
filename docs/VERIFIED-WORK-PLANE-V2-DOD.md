# Verified Work Plane V2 — Production Definition of Done

Gate-by-gate state of branch `spec` against section 51 of the production
hardening plan. Each row is either backed by an executed test or marked open.

## Delivery decision

```text
ARCHITECTURE: PASS
CONTRACTS:    PASS
CONTROLLER:   PASS
EVIDENCE:     PASS
TRUST:        PASS
FRESHNESS:    PASS
VERIFICATION: PASS
TRACEABILITY: PASS
CONVERGENCE:  PASS
ADVERSARIAL:  PASS (A01-A53 and A71, covered across the Linux and Windows legs)
CI:           PASS

CONTROLLER_AUTHORITY:            ADDRESSED, awaiting external review
AUTHORITATIVE_E2E:               ADDRESSED, awaiting external review
PER_EVIDENCE_TRUST:              ADDRESSED, awaiting external review
PER_EVIDENCE_FRESHNESS:          ADDRESSED, awaiting external review

AUTHENTICATED_EVIDENCE:          ADDRESSED, awaiting external review
PROVENANCE_CAPABILITIES:         ADDRESSED, awaiting external review
SUCCESS_CONDITION_AUTHORIZATION: ADDRESSED, awaiting external review
AUTHORIZATION_EVIDENCE:          ADDRESSED, awaiting external review
ROOT_TRANSITION_BINDING:         ADDRESSED, awaiting external review
EXACT_WORK_BINDING:              ADDRESSED, awaiting external review
REGISTRY_SCHEMA:                 ADDRESSED, awaiting external review

APPROVAL_ORIGIN:                 ADDRESSED, awaiting external review
AUTHORITY_STABILITY:             ADDRESSED, awaiting external review
ROOT_CHAIN_RESOLUTION:           ADDRESSED, awaiting external review
HUMAN_APPROVAL_CONVERGENCE:      ADDRESSED, awaiting external review
AUTHORING_FACADE:                ADDRESSED, awaiting external review

APPROVAL_PREDICATE:              ADDRESSED, awaiting external review
GENESIS_TRUST_BOOTSTRAP:         ADDRESSED, awaiting external review
COMMITTED_ROOT_HISTORY:          ADDRESSED, awaiting external review
PREDICATE_PROVIDER:              ADDRESSED, awaiting external review (signature; git_reviewed and ci_verified remain unimplementable)

INITIAL_CONTRACT_ADMISSION:      ADDRESSED, awaiting external review
SIGNER_AUTHORIZATION:            ADDRESSED, awaiting external review
CONJUNCTIVE_PATH_PROVENANCE:     ADDRESSED, awaiting external review
ROOT_CHAIN_CONNECTIVITY:         ADDRESSED, awaiting external review

POLICY_EVOLUTION:                ADDRESSED, awaiting external review
CONTROLLER_ANCHOR_VERIFICATION:  ADDRESSED, awaiting external review

POLICY_ROOT_ATOMICITY:           ADDRESSED, awaiting external review
HISTORICAL_TRANSITION_EVIDENCE:  ADDRESSED, awaiting external review (commit + path + digest)
APPROVAL_SCOPE:                  ADDRESSED, awaiting external review (decided, not left ambiguous)
BOOTSTRAP_TRUST:                 OUT OF SCOPE, declared (ADR-0006, A101)
REUSABLE_ATTESTED_EVIDENCE:      NOT BUILT, designed for

ADVERSARIAL_E2E:                 PASS (A54-A70, A72-A107)

HISTORICAL:   OPEN
PILOT:        OPEN

P0 = not claimable
P1 = not claimable

→ NO-GO
```

`NO-GO` is the plan's own verdict for this state, not a judgement about the
code.

**P0 = 0 is deliberately not claimed here**, and the second review is why the
rule earns its keep. The first round closed five authority findings, every one
held by an end-to-end case, all green on two platforms — and an external
reviewer then found four more P0s in what those cases did not ask. A
hand-written `verification_run` converged. A signature satisfied a policy
demanding CI. Rewriting the command under test turned a failing check into
`CONVERGED`.

Those were corrected — and a third review then found two more P0s, one of them
in the correction itself: the mutation bar's key could be cut by the actor it
controlled, and the first version of the test helper showed exactly how. The
other was an ordering bug, not a missing check: a verification command could
rewrite the authority while it ran.

A fourth review then found two more, and both were the same shape as each
other: something that looked like authority was a statement by the party it was
meant to constrain. A `mutation_approval` the actor wrote and committed
satisfied a policy whose predicate was *named* `review` — because
`predicate_id` was compared as a string while the facts required came from the
same policy. And `WorkController.create()` still established a project's own
policy, root, registry and rules, so every N → N+1 protection could be
sidestepped by choosing a different N.

A fifth review then found two more. Both were the boundary of a round-4 fix
rather than a gap it missed: project trust authenticated the *root* a work used
but not the initial contract that work claimed to be judged by, so an actor
could still choose the bar by creating a sibling work under a legitimate root.
And `signature` proved that Git accepted a signature without ever asking whose,
so any identity the repository's verifier configuration accepted satisfied the
production default.

A sixth review then found the remaining P0 at a different layer entirely: who
authorizes the *first* project trust anchor. Nothing in the runtime does, and
nothing can — a root of trust cannot prove its own legitimacy from data whose
authority comes from that root. That one is answered by declaring the boundary
rather than by building another internal layer.

The seventh review reported **P0 = 0** for the first time, inside the threat
model ADR-0006 declares. Its three findings were consistency and
history-of-proof invariants rather than new ways to manufacture `CONVERGED` —
a different, healthier class of problem than the earlier rounds.

Seven reviews, seven sets of findings, three of them inside a correction. The
standard for closing an authority finding remains external review, and the
record now argues for the rule rather than against it.

## Closed gates

| Gate | What holds it | Where |
| --- | --- | --- |
| Architecture | Frozen invariants preserved; no provider and no language model owns a blocking verdict; the trusted computing base is enumerated; project trust is bootstrapped before work exists and admits each initial contract | `docs/THREAT_MODEL.md`, ADR-0004, ADR-0005 |
| Contracts | Sixteen declared schemas, stable prefixed ULIDs, canonical NFC JSON and SHA-256, portable paths, unsupported schema fails closed | `contracts.py`, A04 |
| Controller | Single writer, explicit mutation semantics, immutable revisions, manifest written last, crash recovery, stale-lock recovery with owner metadata, direct mutation detection | `controller.py`, A01-A06, A51-A53 |
| Evidence | One validated `verification_run`, bound to contract, revision, specification, snapshot, checkout head, registry, policy, approval root and provenance | `evidence.py` |
| Trust | No default reviewed provenance, root pinned to its own commitment, predecessor chain evaluated and acyclic, waivers and human approvals fail closed | `trust.py`, `authorization.py`, A07-A11 |
| Freshness | `STALE_CONTRACT`, `STALE_SCOPE`, `STALE_DEPENDENCY`, `STALE_REPO`, `COMMAND_REGISTRY_CHANGED`, `POLICY_CHANGED`, `ROOT_OF_TRUST_CHANGED`, `VERIFICATION_SPEC_CHANGED` | `freshness.py`, A21-A28 |
| Verification | Argv only, timeouts, process-tree and container termination, bounded streaming output, substance adapters, secret redaction, append-only runs | `runner.py`, `isolation.py`, `substance.py`, A12-A20 |
| Traceability | REQ→AC→Spec→Run and REQ→TASK→paths, relationship scope coverage, human-approval and black-box paths, deterministic structural gaps | `traceability.py`, A29-A35 |
| Convergence | Four verdicts with exit codes 0/1/2/3, no vacuous convergence, no arbitrary mappings, no stale or untrusted evidence, no unauthorized exception | `convergence.py`, A36-A45 |

## CI — closed

Pull request #16 made the `workplane-v2` job execute for the first time. Run
`33687956666`: every job green, including `Verified Work Plane V2` on
`ubuntu-latest` and `windows-latest`, each running the contract, controller,
snapshot, runner, trust, freshness, traceability, convergence, authorization,
substance, adversarial, CLI, integration and pilot suites, the package install
with its console entry point, and the three deterministic scripts.

The Linux leg is what first executed the POSIX branches — `os.kill`,
`killpg`, `start_new_session` — which no local run on this machine could
reach. It also ran the adversarial matrix with **no skips**: the FIFO, device
and symlink cases that Windows cannot create are covered there. The matrix is
therefore complete across the pair, not on either OS alone.

macOS is not in this job. The plan lists it as optional and the existing
`installers` and `hooks` jobs already cover it for the surrounding stack.

## Eighth-round correction, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| A transition's recorded approval digest was never verified | The evaluator reads the approval out of the recorded commit at the recorded path, canonicalizes it and requires the digest to match; any failure leaves the transition unbound, and unbound is invalid | A107 |

## Seventh-round corrections, awaiting review

The seventh review was the first to report **P0 = 0** inside the declared threat
model. Three findings remained; all three are corrected.

| Finding | Correction | Case |
| --- | --- | --- |
| The writer committed states that can never be authority | A root must carry the commitment of the policy it is written with; atomicity then follows from the root-connectivity rule rather than needing a second check | A104 |
| Historical transitions borrowed current provenance | The manifest records the commit that authorized each rotation; the evaluator re-establishes facts from that commit, and an unbound transition is invalid | A105 |
| An approval authorized a destination, not a transition | `mutation_approval` binds `base_digest`; `work_creation_approval` stays content-addressed by explicit decision | A106 |
| Selective rerun still not delivered | Unchanged and still stated: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT` | ADR-0003 §1 |

## Sixth-round corrections, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| The first project trust anchor authorizes itself | **Not fixed — declared.** Genesis is a privileged ceremony inside the trusted computing base; the runtime cannot distinguish a trusted operator from an agent, and the deployment requirement is that trusted bootstrap precedes controlled-agent access. An external trust source is the only mechanical answer and is deliberately not built. | A101, ADR-0006 |
| Policy evolution was unreachable, and history judged by today's rules | Each root carries the policy it was established under; the manifest records the committed policy chain; a transition is judged under its predecessor's policy | A102 |
| The controller wrote under an anchor the evaluator would reject | One `verified_anchor()`, used by the writer and the judge | A103 |
| Selective rerun still not delivered | Unchanged and still stated: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT` | ADR-0003 §1 |

## Fifth-round corrections, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| The initial work contract was self-authoring | A `work_creation_approval` binds the anchor and the exact genesis normative digest; the controller will not write an unadmitted work and the evaluator will not converge on one | A97 |
| `signature` proved validity, never authorization | The anchor pins `authorized_signers` by key fingerprint, and the signer must appear there; the anchor itself must have exactly one commit, or pinning is circular | A98 |
| One signed commit signed a whole path set | The signing identity is resolved per path; a set verifies only when every member does | A99 |
| A predecessor-less root was a second genesis | The controller requires a predecessor plus a transition approval on any root change; the chain terminates only at the pinned genesis | A100 |
| Selective rerun still not delivered | Unchanged and still stated: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT` | ADR-0003 §1 |

## Fourth-round corrections, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| A self-recorded approval satisfied a predicate named `review` | A predicate is a closed mechanism with a fixed fact requirement; the policy may add to it, never subtract | A94, with the satisfied-predicate control |
| No provider implemented any independent predicate | `signature` is implemented against Git's own verification of the commit that last wrote the observed paths; it is now the documented production default | A94 control, A95 anchor case |
| Work creation established its own root of trust | Project trust is bootstrapped before work exists and pins the genesis root; an unpinned work is unevaluable and a foreign root is refused | A95 |
| `root_history()` read revision directories | The committed root chain lives in the manifest, and each historical root is re-digested when read | A96 |
| Selective rerun still not delivered | Unchanged and still stated: `REUSABLE_ATTESTED_EVIDENCE: NOT BUILT` | ADR-0003 §1 |

## Third-round corrections, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| The mutation approval was self-issuable | It is a path; the controller observes the artifact's own provenance | A91, A92 |
| Authority could change during evaluation | Re-read and compared after the runs; drift is unevaluable and therefore INVALID | A93 |
| A rotated root could never validate in production | Predecessors resolved from earlier revisions of the same work | covered by the governed path |
| A human-approval-only contract could never converge | Machine evidence is required only of specifications that expect a run | `test_convergence_ignores_narrative_and_blocks_failures` |
| The CLI could not perform an authorized update | `work update --approval --delete` | `test_workplane_cli` |
| Selective rerun was silently given up | Named as two modes: local secure (built) and attested reusable (designed for, not built) | ADR-0003 §1 |

## Second-round corrections, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| A hand-written verification_run converged | The evaluator executes the declared verifications and judges only what it produced; recorded runs are an audit trail, and there is no evidence-directory parameter | A72, A73 |
| A clean checkout capped the provenance of artifacts living elsewhere | Two observations, per object: the checkout for the code, the normative artifacts at their own location | A74-A76 |
| Provenance was a numeric ladder, so SIGNED satisfied CI_APPROVED | Independent facts a policy names individually; no fact substitutes for another | A77-A79 |
| Rewriting the command under test turned failure into CONVERGED | Every normative change needs a mutation_approval issued under the policy in force before it, naming the exact next state | A80-A83 |
| A waiver's approval_provenance proved itself | The claim is not read; the artifact's observed facts are | A84, A85 |
| A transition approval named a UID, not a state | It binds successor_commitment, a digest of the candidate's content | A86 |
| Evidence bound only by contract digest | Binding also checks work UID and contract revision, both derived from the manifest | A87, A88 |
| The registry was validated by two different rules | One validator, called by the contract and by the runner | A89, A90 |

## First-round corrections, awaiting review

| Finding | Correction | Case |
| --- | --- | --- |
| A caller could supply the contract, policy, root and freshness | `evaluate_work(work_dir, repository_root)` derives all of it from committed state; the loose helpers moved under `ainative debug` and label themselves `authority: none` | A54, A65, A66, A68 |
| A provenance string proved itself | `provenance.observe()` reports what the checkout supports; every declared level is capped at it | A55, A56, A61 |
| Trust and freshness came from `evidence[0]` | Each run carries its own `EvidenceAssessment`; only individually eligible runs count | A58, A59, A69, A70 |
| Freshness could be supplied as a fixture | Recomputed from the checkout per specification | A57 |
| A normative artifact needed no schema | Normative names must validate; other names are marked non-normative and never read | A64 |
| A partial mutation deleted the rest | Explicit set and delete over the previous revision | A63 |
| A predecessor link was treated as authorization | A successor must carry a `transition_approval` naming that exact successor | A62 |
| Waiver eligibility was a blocklist | An allowlist of eight completeness gaps | A67 |
| A file could be rewritten while hashed | Size, mtime and inode compared before and after | A71 |

## Open gates

### Historical — never executed

No blind historical validation has been run. The protocol is written down in
[the historical validation protocol](verified-work-plane-v2-historical-validation-protocol.md);
its case table is empty. The synthetic script that used to claim this gate was
renamed to `scripts/workplane_structural_regression.py`, which is what it is.

Closing it needs a real pre-fix commit and a defect hidden from whoever authors
the contract. One agent cannot hold both roles.

### Pilot — one harness, synthetic items

`scripts/workplane_pilot.py` and `scripts/workplane_harness_matrix.py` both
report `external_harness: false`, and section 47 states plainly that a direct
API against a CLI facade is not two AI harnesses. The five-item shape is a
smoke pilot, not production evidence.

`docs/qualification/*.json` records that two independent harnesses reproduce
the four qualification gates at a commit. That is gate reproducibility, not the
pilot protocol of section 48, which requires per-item contracts, revisions,
reruns, interventions and friction across two real features, a bugfix, a
refactor and a hotfix.

## Local verification at the time of writing

```text
python -m unittest <16 V2 modules + vault + hooks + ai_docs> -q
→ 153 V2 tests, OK (2 skipped: FIFO and symlink creation on Windows)
→ 38 ai_docs tests, OK;  40 scripts tests, OK
python scripts/measure_scope.py       → figures match AGENTS.md
python scripts/validate_conventions.py → thresholds agree
```

The same suites run in CI on Linux and Windows, where the two locally skipped
cases execute.

## Residual risks, stated

- PID reuse in stale-lock recovery: a recycled PID reads as alive, so the
  controller errs toward refusing to reclaim rather than breaking a live lock.
- Secret redaction is pattern-based. It is defense in depth; persisted evidence
  keeps digests and a bounded preview rather than full logs for that reason.
- Assigning a spawned command to its OS container has a microsecond window
  after start; a process created inside it is caught by the PID-tree fallback.
- `git_reviewed` and `ci_verified` are not observable from a checkout, so a
  policy requiring either cannot be satisfied by this build. That is
  fail-closed, and it is a real functional limit, not a detail. The predicate
  with a working provider is `signature`, and it is the documented default.
- A transition approval is a record, not a signature. In a single-maintainer
  repository the system protects against agent self-approval, accidental
  weakening, stale evidence, configuration drift and unreviewed automated
  modification — it cannot protect against the legitimate sole maintainer
  deliberately changing both the rules and the approvals.
- The snapshot race check compares size, mtime and inode; a rewrite preserving
  all three is undetected.
- Convergence now executes the declared verifications, so a verdict costs a
  full run and evidence is not reusable across invocations. Reuse needs an
  independently verified attestation, which this build cannot check.
- Freshness no longer gates staleness on the in-process path — it catches a
  checkout moving underneath a running verification. Stale *reuse* is prevented
  by not reusing, not by detection.
- **Genesis is not verifiable by the runtime.** Before a trusted anchor exists,
  a controlled actor can generate its own key, authorize it, sign the anchor
  and converge — every check passing truthfully. The mitigation is a deployment
  requirement (trusted bootstrap precedes controlled-agent access), not a
  mechanism. ADR-0006 and case A101 state it; an external trust source is the
  only mechanical answer and is not built.
- A broken root chain surfaces as `ROOT_OF_TRUST_INVALID` inside the reasons
  an individual run was ruled ineligible for, rather than as a standalone gap,
  so the verdict is `NOT_CONVERGED` where `INVALID` would classify it better.
  It never produces a false `CONVERGED`; it is noted rather than changed,
  because the eighth review asked for a narrow round.
- A historical transition's facts are re-established from the commit that
  authorized it, which is immutable — but against the signer set the anchor
  pins *today*. Removing a signer therefore invalidates that identity's earlier
  transitions. Fail-closed, and locally the honest reading: the project no
  longer trusts them.
- A `work_creation_approval` is content-addressed by decision, so the same
  admission may create more than one work carrying byte-identical contracts.
  ADR-0007 §3 records why and what to add if that is ever wrong.
- Under the `recorded_owner_ack` predicate — at either level, the mutation
  approval or the project trust anchor — an actor with commit rights is the
  whole bar. The fourth round named that posture rather than removing it; only
  `signature` excludes an actor without the key, and only after genesis.
- The project trust anchor is a file. Under `recorded_owner_ack` an actor can
  write and commit one. Under `signature` it cannot produce one that verifies,
  and rewriting an existing anchor now makes it establish nothing at all,
  because an anchor must have exactly one commit in its history.
- That immutability has an operational cost: changing a governed project's
  authorized signers, including after a lost key, requires establishing a new
  project trust anchor rather than editing the existing one.
- Resolving the signing identity costs one `git log` per observed path. A very
  large declared scope makes an observation proportionally slower.
- `scripts/workplane_pilot.py` calls the pure `converge()` kernel directly, not
  `evaluate_work`, so it does not exercise the trust anchor or the mutation
  bar. It is labelled `authority: smoke_pilot_only` for exactly this reason and
  is not evidence about authority.
- Authority drift is compared before and after the verification runs, not
  continuously. A change made and reverted within a single run is undetected.
- Convergence re-executes every declared verification. For a large suite that
  is prohibitive, and the attested-evidence mode that would fix it is designed
  for but not built.
