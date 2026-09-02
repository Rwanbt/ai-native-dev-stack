# Verified Work Plane V2 — Architecture Baseline

## Purpose

The Verified Work Plane (V2) will let an agent or developer represent declared work,
run approved verification independently, and decide deterministic convergence for one
repository state. This document records the PR-00 boundary; it does not add runtime
behaviour or make a future component authoritative yet.

## What exists today

| Existing owner | Responsibility | V2 relationship |
| --- | --- | --- |
| `install.py` | Per-project installation of AI-doc tooling, skills, rules, and an optional pinned gstack checkout | Reuse only as a distribution precedent; do not add the V2 runtime here before a distribution ADR. |
| `scripts/install_agents.py` and `scripts/vault_protocol.py` | Global harness setup, vault discovery, slug validation, path confinement, maintenance-lock and validator checks | Reuse the trust-boundary patterns; V2 must not duplicate or reinterpret vault authority. |
| `scripts/vault_sync.py` | Validates a v4 vault before staging and pushing sync changes | Remains vault synchronization, not Work Contract storage. |
| `hooks/session-start-memory` and `hooks/session-end-save` | Read/write optional session memory via local Obsidian REST endpoints | Remain optional providers; no convergence verdict may depend on them. |
| `.github/workflows/ci.yml` | Cross-platform Python, hook, installer, and static convention gates | Future V2 commands must be headless and add explicit CI gates rather than altering existing gate meaning. |
| `stack/agents/anti-debt/` | Independent deterministic debt analysis | May contribute read-only findings later; it must not decide whether a Work Contract converges. |

## Target boundary

```text
trusted project policy + registered commands
                 │
                 ▼
           Work Controller
                 │
       immutable Work Contract revisions
                 │
                 ├───────────────┐
                 ▼               ▼
       Verification Runner   Repository Snapshot
                 │               │
                 └───────┬───────┘
                         ▼
               Deterministic Convergence
                         │
                    verdict + gaps

optional, read-only inputs: vault memory | Graphify | ADRs | anti-debt
```

The Work Contract is the sole operational authority. Narrative plans and vault memory
provide provenance and context but never become executable policy by prose alone.

## Ownership rules

- The Work Controller is the only supported normative writer.
- The command registry and project policy are part of the trust base. A controlled
  implementation cannot silently change either and then claim its own success.
- The runner receives a registered `argv` array, never an arbitrary shell string.
- Verification runs and convergence records are append-only evidence, bound to a
  captured repository state.
- A language model may suggest gaps or prose, but never emits a blocking PASS/FAIL
  verdict without deterministic evidence.

## PR-00 decisions deferred

- **Distribution decision:** V2 will be a first-party Python package named
  `ainative_workplane`, with `python -m ainative_workplane` as the canonical developer
  invocation. Shell and PowerShell entry points may be thin wrappers only. The package
  owns its runtime and schema compatibility version; the root `VERSION` remains the
  version of the existing AI-Native Dev Stack. PR-01 must define package metadata and
  schema-discovery compatibility, but must not change this ownership decision.
- The on-disk V2 format, schema tooling, UID implementation, and controller are PR-01
  and PR-02 work, after review.
- Graphify, Obsidian, Spec Kit, and anti-debt integrations remain providers rather than
  core dependencies.

## Trust baseline and mutation protocol

The portable default is `git_reviewed`: contract creation records an approved Git commit
and canonical digests for `.ai-native/config/commands.json` and `policy.json`. A local
commit is `GIT_RECORDED`, not automatically reviewed. If either file is dirty, absent
from the approved commit, or differs from its recorded digest, the run is
`local_untrusted` and cannot be represented as `git_reviewed` evidence.

The initial manifest is created only by the Work Controller. Later loads canonicalise
each referenced artifact and compare its digest with the manifest: mismatch becomes
`UNEXPECTED_MUTATION`; an unreadable pointer or invalid manifest becomes `INVALID`.
Controller staging lives beneath `<work>/.staging/<transaction-id>/`, never system temp.
It writes staged artifacts, promotes them to immutable revisions, then atomically replaces
the manifest last. Directory/file sync is best effort where the platform supports it; it
is not a claim of power-loss durability.

Verification substance is runner-specific: PR-04 owns adapters for known tools and a
documented fallback for custom commands. Exit status alone never proves substance.

## Test path planned for later phases

```text
create contract → mutate through controller → implement repository change
→ capture snapshot → run registered command → inspect substance
→ converge or report deterministic gaps
```

Each arrow needs an integration test. Mutation, snapshot, path safety, registry
tampering, stale scope, crash point, and prompt-injection cases need negative tests.
