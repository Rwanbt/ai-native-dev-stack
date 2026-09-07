# Implementation Delta — V1 branch vs final contracts (per external review)

How to read: `Final` restates the external review (V3.3.1 unseen locally —
treat as CLAIM, not quote). `Existing` is verified on `a3f1a83`.
Next step for every TBD row: fill against the frozen document when provided.

| Final contract | Existing branch | Status | Action |
|---|---|---|---|
| 4 state classes (Canonical/Transient/Derived/Durable Control) | ADR-0011 says 3 planes; store+audit+transient under `.ai-native/knowledge/` | CONFLICTING | update architecture + storage layout |
| Local Control Payload (gitignored) vs Project Audit Control (Git-backed) | single dir, `.ai-native/` not ignored at all | CONFLICTING | split paths + gitignore management |
| root-specific identity_key + grammar version + assertion hash | absent (grep empty); scope dict + digests only | ABSENT (pending doc) | single parse/resolve/validate/normalize/hash primitive |
| Claim source binding (path/anchor/digest, CLAIM_STALE) | evidence locators + staleness signals, no per-claim binding | PARTIAL | bind claims to canonical spans |
| One ContextPlanner, all callers unified | `retrieval.assemble` used by CLI only; assembler/hooks/skills independent | PARTIAL | unify callers + no-second-engine test |
| Tier-A overflow explicit failure | hard budgets + `dropped` counts in bundle | PARTIAL | confirm failure semantics vs final |
| Cross-project isolation E2E | no dedicated test (disclosed gap) | ABSENT | USE_PROD_SECRET_X + outside-root-YAML probes |
| Working continuity | checkpoint/restore/TTL/crash tests green | PRESENT? | verify vs final K3 |
| Conflict-before-dedup ordering | verify runs canonical+dedupe+evidence per call | PRESENT? | verify vs final K4 |
| K5 measurement gate (STOP/NARROW/FULL) | no metrics collection (telemetry-free by design) | ABSENT | define measurement before promotion merge |
| Promotion trust (VERIFIED_WORKPLANE_AUTHORITY / EXTERNAL_ATTESTATION) | `--approve` string, forgeable audit | CONFLICTING for K5 | quarantine; reuse shared authority |
| promotion_commit_ref | absent (base/result digests only) | ABSENT (pending doc) | inspect |
| Section-granularity result digest | file-level digests only | PARTIAL | narrow granularity |
| representation_health final semantics | `reconcile` + statuses | PARTIAL | align semantics |
| Fresh-clone promotion | absent | ABSENT (pending doc) | add AQ |
| Trust replay protection | absent from branch and report | ABSENT | add iff K5 proceeds |
| QUAL-T | unknown locally | ABSENT | K0-A |
| Thresholds (Jaccard 0.6, sufficiency, budgets) | named defaults, unbenchmarked | ACCEPTED as experimental | telemetry/bench before hardening |
| Doctor on corruption | informative + JSON status (text `production_qualification` missing) | ACCEPTED with fix queued | expose qualification FAIL in text |
| `DERIVED_PATHS` registry | exists, empty by construction | ACCEPTED | keep; register future caches |

Quarantined (do not merge as final): promotion path, `--approve` trust
assumption, last-writer-wins append, V1 phase numbering/docs, any claim
of completeness. Directly reusable after verification: schemas, state
machine, secret scanning, checkpoints, dedup helpers, provider
protocols, GraphFileProvider, staleness primitives, consolidation
advisory, import quarantine, doctor reporting, security tests.