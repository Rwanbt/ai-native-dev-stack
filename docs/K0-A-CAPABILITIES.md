# K0-A Capability Matrix — executed

> [!WARNING]
> HISTORICAL K0 CAPABILITY PROBE.
> This document records pre-convergence evidence (2026-09-07) and MUST NOT be
> used as the current operational capability matrix. Rows such as
> `knowledge promote --approve`, `ContextPlanner ABSENT`, `locking unused` and
> `P1 stands` describe the pre-convergence state this project has since
> replaced; they are kept as the record of what was measured then.
>
> Current state:
> `docs/knowledge/KNOWLEDGE-CONVERGENCE-MATRIX.md`

Evidence collected on `knowledge-lifecycle@a3f1a83`, re-verified identical
on `main@599b765` (`git diff main..a3f1a83` is empty for every cited path:
`ainative/lifecycle`, `ainative_workplane`, `tools`, `hooks`, `skills`,
`.gitignore`). Docs-only; zero runtime in this PR.
Method: each row was probed by command or direct read; proofs cite the
exact location. Labels: PRESENT / PARTIAL / ABSENT / UNSAFE (V3.3.1 S32).

## QUAL-T — executed, not asserted

Probe (2026-09-07, same shell as the controlled agent): created a scratch
project and ran `ainative knowledge retrieve` directly — exit 0, bundle
returned. The approval action (`knowledge promote --approve`) is the same
CLI surface, invocable identically (exercised in smoke tests on
`kdemo`/`ke2e` scratch projects).

```text
QUAL-T result: TRUST_BOUNDARY_NOT_SEPARATED
capability_status = NOT_SEPARATED (this execution profile)
```

This is not an architecture failure (V3.3.1 S27): it means ceremony-only
promotion in THIS profile stays UNVERIFIED unless Verified Work Plane
authority or external attestation is used. Any deployment claiming
SEPARATED must re-run this probe in the locked-down profile.

## Trust root accessibility (V3.3.1 S17/S27)

| Item | Finding | Proof |
|---|---|---|
| Trust-root location | `.ai-native/trust/project_trust.json` | `ainative_workplane/bootstrap.py:41` (`TRUST_RELATIVE`), schema `project_trust` (`bootstrap.py:87`) |
| Controlled actor read | YES | read back a scratch anchor as the agent user |
| Controlled actor write | YES | overwrote the scratch anchor (`forged:true`) as the agent user |
| Signer accessibility | NO signing identity configured | `git config user.signingkey` unset, `commit.gpgsign` unset |
| Verdict (this profile) | **UNSAFE** for production trust qualification (V3.3.1 S33 branch) | controlled actor reads+writes root material |

## Authority verifier + reference format

| Item | Status | Proof |
|---|---|---|
| Existing authority verifier | PRESENT (primitives) | `ainative_workplane/evaluator.py:334` `establish_authority(work_dir, repository_root)`; `evaluate_work` (`:379`); `provenance.signature_verified(paths, authorized_signers=...)`; `predicates.py` closed predicate set |
| Authority reference format | PARTIAL (convention, no single extractor) | references are artifact paths + digests bound in the manifest chain (ADR-0007 S3, content-addressed decisions); no one `resolve_authority_ref()` function exists — extraction work item, not a copy |
| Approval-digest binding (knowledge side) | ABSENT | no `approval_digest` concept; `--approve` is free text in local JSONL |

## Git resolvers

| Resolver | Status | Proof |
|---|---|---|
| Introduction-commit (`recording_commit`) | PARTIAL | `ainative_workplane/provenance.py`: `recording_commit(target, path)` (last writer), `commit_count`, per-path signing — per-object primitives, not named resolvers |
| Tree-at-commit (`blob_at_commit`) | PARTIAL | same module: `blob_at_commit(target, commit, path)` reads exact bytes |
| Path-history resolver | ABSENT | only `git log --format` fragments; `knowledge.git_changed` uses `status --porcelain` + `diff --name-only` |

## Lifecycle / safety / context primitives (carried from pre-erratum inventory)

| Primitive | Status | Proof |
|---|---|---|
| Transaction + recovery | PRESENT (lifecycle), PARTIAL (knowledge: atomic-replace only, no journal) | `ainative/lifecycle/transaction.py` |
| Path confinement | PRESENT, reused | `ainative/lifecycle/paths.py`; knowledge explicit-target + locator validation |
| Inter-process locking | PARTIAL (exists, unused by knowledge) | `ainative/lifecycle/lock.py` (`LockInfo`, owner-alive); zero knowledge imports — P1 stands |
| .gitignore management (knowledge store) | ABSENT | `.ai-native/` not ignored; no state/audit split |
| Ownership records (knowledge store) | ABSENT | ADR-0009 classes cover lifecycle files only |
| Schema versions / migrations | PARTIAL | versions present (4 records), zero migration functions |
| Single ContextPlanner | ABSENT | `retrieval.assemble` called only by `ainative/cli.py`; assembler/hooks/skills independent |
| Freshness / provenance engines | PARTIAL each, separate by design | `ainative_workplane/freshness.py`, `provenance.py`; knowledge best-effort mirrors |
| Graphify output | PARTIAL | `graphify-out/graph.json` convention + hook; file adapter only |
| Vault code path | ABSENT | operator-side only |
| Semantic provider | PARTIAL | protocol + degraded + fakes; no real adapter |
| N-writers zero-loss test | ABSENT | sequential only |

## QUAL-T ledger entry

```text
profile: single-user dev shell (agent == OS user)
result: TRUST_BOUNDARY_NOT_SEPARATED
evidence: direct CLI invocation exit 0 (scratch project, 2026-09-07)
consequence: ceremony-only K5 stays UNVERIFIED here (V3.3.1 S7/S12)
```