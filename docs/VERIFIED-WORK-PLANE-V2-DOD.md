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
ADVERSARIAL:  PASS (fully covered across the Linux and Windows legs)
CI:           PASS
HISTORICAL:   OPEN
PILOT:        OPEN

P0 = 0
P1 = 2

→ NO-GO
```

`NO-GO` is the plan's own verdict for this state, not a judgement about the
code. The engine gates are closed; the gates that remain open are the ones
that require evidence this branch cannot produce about itself.

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
python -m unittest <14 V2 modules + vault + hooks> -q
→ 103 tests, OK (2 skipped: FIFO and symlink creation on Windows)
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
