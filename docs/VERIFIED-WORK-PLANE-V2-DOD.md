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

ADVERSARIAL_E2E:                 PASS (A54-A70, A72-A90)

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

Those are corrected now, with the same kind of evidence that proved
insufficient last time. The standard for closing an authority finding remains
external review.

## Closed gates

| Gate | What holds it | Where |
| --- | --- | --- |
| Architecture | Frozen invariants preserved; no provider and no language model owns a blocking verdict; the trusted computing base is enumerated | `docs/THREAT_MODEL.md` |
| Contracts | Twelve declared schemas, stable prefixed ULIDs, canonical NFC JSON and SHA-256, portable paths, unsupported schema fails closed | `contracts.py`, A04 |
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
python -m unittest <17 V2 modules + vault + hooks> -q
→ 132 tests, OK (2 skipped: FIFO and symlink creation on Windows)
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
- `GIT_REVIEWED` and `CI_APPROVED` are not observable from a checkout, so a
  policy requiring either cannot be satisfied by this build. That is
  fail-closed, and it is a real functional limit, not a detail.
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
- A mutation approval is a record, not a signature. It stops an agent from
  silently rewriting its own bar; it does not stop a sole maintainer who
  writes both the rules and the approvals.
