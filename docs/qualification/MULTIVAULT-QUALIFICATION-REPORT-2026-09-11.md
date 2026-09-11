# Multi-Vault Qualification Report — 2026-09-11

Scope: Claude Code 2.1.220 on Windows, tested provider/model/runtime set, commit `80b3579`.
Qualification is per capability set, never per harness.

## Profiles

| Profile | Enabled capabilities | Qualification |
|---|---|---|
| A | Claude + read-only vault | **GUARDED QUALIFIED** |
| B | Claude + vault + thin MCP/REST | **GUARDED QUALIFIED** |
| C | Claude + vault + semantic retrieval | **NOT QUALIFIED** — Smart Connections empirical evidence UNKNOWN; sensitive semantic denies by default (correct fail-closed) |
| D | Claude + vault + semantic + governed Git | **NOT QUALIFIED** — inherits Profile C's semantic dependency; the Git capability itself is VERIFIED |

ENFORCED: **NOT YET QUALIFIED** (requires physical account/container separation plus an external authenticator; Windows Job Object containment is VERIFIED but insufficient for ENFORCED-AUTHENTICATED).

## Gate evidence

- Launch path: containment (PR #118), provider principal, endpoint routing, auth store, carried state A→B, provider selection, project-instruction policy, SensitiveLaunchGate, thin exec wrapper. 47 Claude tests green.
- Gate 1 vault binding / root freshness: ADR-0015 primitive digest, resolver admission path, doctor CLI, real-directory E2E (replaced root, junction swap, copied binding, measurement failure). INTEGRATION DONE.
- Gate 2 MCP/REST: instance identity required (fail closed), governed-credential marker, REST deny matrix, redirect refusal with real 302 server, epoch rollover. INTEGRATION DONE.
- Gate 3 persistent memory: ADR-0013 §8 exact-match namespace, real-store E2E, operator-approved migration. INTEGRATION DONE.
- Gate 4 semantic egress: admission and drift revocation enforced; empirical plugin qualification UNKNOWN → NOT QUALIFIED for semantic-enabled profiles.
- Gate 5 governed Git: submodule/LFS/promisor DENY, unapproved and secondary remotes, config-file and hook neutralization, mid-transfer drift detection, push governance. INTEGRATION DONE.
- Gate 6 canaries: real plant/scan/cleanup sweep, exit contract 0/1/2, frozen error taxonomy, GUARDED honesty statement, real-filesystem tests. INTEGRATION DONE.
- Gate 7 fault injection: 24-scenario matrix executes the canonical fail-closed tests of every owner; all green.

## Honesty

Under GUARDED, canaries and drift detection detect leaks and operational errors; they do not resist a hostile same-OS-user. No unknown sensitive capability is ever promoted: absence of evidence denies.

P0 = 0, P1 = 0. Known non-security flake tracked as issue #121.
## Semantic qualification attempt - 2026-09-11 (real instance)

Empirical run against the live Smart Connections instance (plugin 4.7.2, transformers/bge-micro-v2 local embeddings, both vaults open simultaneously).

- Network: NO external connections observed (netstat, only loopback listeners).
- Background indexing: ACTIVE (reimport cycles advance without user action).
- Cross-vault isolation: VERIFIED (neither vault store references the other).
- Controlled embed test: REPRODUCIBLE FAILURE - two probe notes were not embedded; embedding:error incremented on every attempt; the index is frozen.
- Verdict: Profile C = NOT QUALIFIED (blocking property: runtime indexing/embedding integrity). Profile D inherits. Evidence: docs/spikes/multivault/SEMANTIC-RUNTIME-EVIDENCE-2026-09-11.json.
- Minimum user action: repair the embedding model cache or reinstall the plugin in the live vault, then re-run the controlled embed test. Qualification resumes automatically when a probe note lands in smart_sources.ajson.

## ENFORCED boundary evaluation - 2026-09-12

- Machine: Windows Pro build 26100, session NOT elevated. Windows Sandbox absent, VirtualBox absent; Hyper-V/Docker present but require administrator rights.
- Dedicated account, Sandbox and VM options: BLOCKED (admin required) - proven, not assumed.
- WSL2: different platform tuple (Linux), forbidden as equivalence by the frozen architecture; also mounts fixed drives by default.
- AppContainer desktop boundary: technically correct user-level path, but requires a new launcher subsystem with its own qualification - recommended V2, out of frozen V1 scope.
- Proven partial boundary: Windows Job Object containment (VERIFIED) - sufficient for GUARDED, insufficient for ENFORCED-AUTHENTICATED.
- Verdict: ENFORCED-AUTHENTICATED NOT YET QUALIFIED. Minimal external prerequisite: an elevated session or a pre-provisioned boundary (dedicated local account, enabled Windows Sandbox, or VM image). Evidence: docs/spikes/multivault/ENFORCED-BOUNDARY-EVALUATION-2026-09-12.json.

## Correction 2026-09-12 (semantic evidence)

The first semantic evidence overstated the defect: probes were imported correctly, but the store is sharded per model fingerprint and the initial greps read the wrong shard. The corrected blocking property is narrower and precise: source-level embeddings of new items never complete in the Electron runtime (embedding.history stays empty while import succeeds; paire

## Final semantic qualification 2026-09-12 - Profiles C and D GUARDED QUALIFIED

Second correction: the semantic pipeline was never broken. Vectors live in the in-memory vec/vecs structures and the model-fingerprint file, not in the serialized embedding.history field. Definitive proof via a temporary CDP session on the live app: 3/3 probe cycles embedded (384 dims, <15s each), retrieval cosine 0.5608 on a targeted query, 1301 indexed items, embeddings fully local. Config restored, probes deleted, app relaunched without the debug port. Profile C = GUARDED QUALIFIED. Profile D = GUARDED QUALIFIED (Git VERIFIED + C qualified; the capabilities share no authority - verified in the frozen owners). ENFORCED-AUTHENTICATED remains WAITING_FOR_EXTERNAL_PREREQUISITE (one elevated provisioning command).

## Scope correction - 2026-09-12 (official)

The Multi-Vault threat model is now explicit: MULTI-VAULT GUARDED provides strong isolation between vault/security domains inside AI Native's governed execution paths. It prevents wrong vault selection, wrong workspace-vault binding, cross-vault memory/semantic/MCP/Git reuse, wrong endpoints and instances, wrong namespaces and provider contexts, stale domain state, implicit fallback and cross-vault autoload.

It does not claim protection against a malicious process running as the same OS user outside AI Native's governed execution paths. This limitation is documented, not hidden.

ENFORCED (dedicated Windows account, OS-level ACL isolation, per-principal network boundary, external authenticator, ExecutionBoundaryDigest) is reclassified as OPTIONAL HIGH-ASSURANCE HARDENING - experimental/future, tracked separately, and not a condition for the main plan.

FINAL VERDICT: MULTI-VAULT GUARDED - PRODUCTION READY.
Profiles: A GUARDED QUALIFIED - B GUARDED QUALIFIED - C GUARDED QUALIFIED - D GUARDED QUALIFIED.
Optional ENFORCED hardening: EXPERIMENTAL - NOT QUALIFIED (separate verdict, does not block).
