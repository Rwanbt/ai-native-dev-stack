# K0-A Capability Evidence — Knowledge Lifecycle branch

Pinned commit: `a3f1a83` (branch `knowledge-lifecycle`).
Purpose: record which primitives the branch provably has before any
realignment, so the V3.3.1 delta cannot be argued from memory.
Status labels: PRESENT / PARTIAL / ABSENT / UNSAFE / TBD.
TBD means the final contract is unseen locally (V3.3.1 not on disk);
the existing side is still inventoried exactly.

## Lifecycle / safety primitives

| Primitive | Status | Proof |
|---|---|---|
| Transaction + recovery (journal, backup, commit-last, repair) | PRESENT in lifecycle; PARTIAL for knowledge | `ainative/lifecycle/transaction.py` (563 lines, `PREPARED/APPLYING/COMMITTED/ROLLED_BACK`); knowledge promotion reuses atomic-replace only, no journal |
| Path confinement (resolve, symlink/junction walk, case policy) | PRESENT, reused | `ainative/lifecycle/paths.py` (`resolve_within`, `is_within`); knowledge uses it for explicit targets + own locator validator |
| Inter-process locking | PARTIAL (primitive exists, unused by knowledge) | `ainative/lifecycle/lock.py` (`LockInfo`, `lock_path`, owner-alive); zero imports from `ainative/knowledge/` — concurrent appends unprotected (P1 stands) |
| .gitignore management | ABSENT for knowledge | `.ai-native/` is not ignored at all (`git check-ignore` empty); no state/audit split; installer manages one `.gitignore` line for its own files only (ADR-0009) |
| Ownership (classified paths + install-time digests) | PARTIAL | ADR-0009 4 classes + digests for lifecycle-managed files; knowledge store files carry no ownership record |
| Schema versioning + migrations | PARTIAL | `schema_version` on lifecycle state (1), candidate (1), working (1), checkpoint (1); zero migration functions in tree |

## Context / knowledge primitives

| Primitive | Status | Proof |
|---|---|---|
| Context Assembler + consumers | PRESENT as independent paths; unification ABSENT | `tools/ai_docs/assemble_context.py` consumed by `skills/verify-ai-docs`; `ainative/knowledge/retrieval.py:assemble` consumed ONLY by `ainative/cli.py` (`knowledge retrieve`) |
| Freshness evaluation | PARTIAL | `ainative_workplane/freshness.py` (`STALE_*`, cases A21-A28); knowledge has promotion-staleness signals + TTL, no shared engine |
| Provenance observation | PARTIAL, deliberately separate | `ainative_workplane/provenance.py` (independent boolean facts); `ainative/knowledge/provenance.py` best-effort, no workplane import (ADR-0011) |
| Graphify output + hook | PARTIAL | Convention `graphify-out/graph.json` + `hooks/pretool-graphify-inject` (existence check only); `GraphFileProvider` parses nodes/edges best-effort, no daemon |
| Vault integration | PARTIAL, no code path | Vault exists operator-side; `scripts/vault_protocol.py` cited by THREAT_MODEL; knowledge has zero vault imports |
| Semantic provider | PARTIAL (contract only) | `SemanticProvider` protocol + degraded behavior + fakes; no real adapter in tree |
| Git resolvers (introduction-commit, tree-at-commit, path-history) | ABSENT | knowledge `git_changed` uses `status --porcelain` + `diff --name-only` only; workplane uses per-object `rev-parse/log/show`, not the named resolvers |
| QUAL-T | TBD | term unknown locally (grep empty across repo + project vault) |

## Authority / trust primitives

| Primitive | Status | Proof |
|---|---|---|
| Work Plane authority verifier | PRESENT, unintegrated | evaluator/convergence/predicates + adversarial suite; zero imports from knowledge (verified by grep + test) |
| authority_ref format / approval-digest binding | ABSENT | grep empty; `--approve` is a free-text string recorded in local JSONL |
| Trust-root location + accessibility / signer accessibility | PARTIAL | workplane trust anchors + bootstrap (ADR-0004/5/6, `seed_verified_history` fixtures); knowledge promotion audit is a local file appendable by any writer — forgeable by construction |
| N-writers zero-loss persistence + audit monotonicity test | ABSENT | only sequential-write test exists |

## Quarantine statement (external review, accepted)

Until V3.3.1 trust integration lands, the whole promotion path
(`promotion.py`, `policy.py`, `knowledge promote`) is STANDARD /
UNVERIFIED: usable as a careful local patch tool, never as
production-trust-qualified promotion. No runtime change accompanies
this statement; enforcement is by review discipline, not by mechanism.