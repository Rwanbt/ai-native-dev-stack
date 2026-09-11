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