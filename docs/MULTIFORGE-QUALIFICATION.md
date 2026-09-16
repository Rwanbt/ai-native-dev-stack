# Multi-Forge qualification report

**Base commit:** `multiforge` head `6f4946b` plus the documentation commit that
carries this report. **Architecture:** frozen (Multi-Forge v1.3.2-final;
ADR-0017/0018/0019). **Execution:** local, issue-driven; the full CI matrix
runs when the branch is proposed for `dev`.

This report states what was verified, with which evidence, and what was not.
Declared support never exceeds qualified support (`SUPPORT.md`, ADR-0019 §13).

## What was delivered

| Stream | Deliverable | Evidence |
|---|---|---|
| PR-0A | Release transport credential confinement (`transport.py`) | 23 tests; characterization probe recorded pre-fix |
| ADR-MF-01/02/03 | ADR-0017/0018/0019 accepted | merged documents |
| PR-0B | V2 forward bridge (`CLI_UPDATE_REQUIRED`) + publication gate | 5 tests; `scripts/check_bridge_release.py` + 9 gate tests |
| PR-1 | Feature model, State V2, atomic switching, GitLab templates | 34 tests + 309-suite regression |
| PR-2 | Work Authority resolver, claim grammar, journal, policy docs, distributed template | 27 tests; policy purity tests |
| PR-3 | `forge detect/status`, doctor extension, status parity | 7 observation tests |
| PR-4 | Source resolver, ReleaseManifest V3, providers, updater wiring | 19 + 32 + 16 + 5 tests |
| PR-5 | GitLab provider (V3 contract), purity tests | 10 provider tests + 7 purity tests |

## Platform matrix

| Platform | Status |
|---|---|
| Windows (local) | GREEN — the full local suite (314 lifecycle + CLI/knowledge/machine suites) |
| Linux, macOS | PENDING — CI runs on the `multiforge` → `dev` proposal; not yet executed |

## Forge qualification

| Tuple | Status |
|---|---|
| Generic Git | GREEN — `feature switch none`, zero-feature states valid, observation resolves `UNAVAILABLE` |
| GitHub.com | GREEN for the release source (existing qualified releases + provider contract tests); GREEN for work management (mapping + observation) |
| GitLab.com | Provider implemented and contract-tested against a scripted GitLab API. **Live-service qualification UNTESTED — not declared supported** |
| GitLab Self-Managed | UNTESTED — not supported |
| GitHub Enterprise Server | UNTESTED — not supported |

## E2E scenarios A–Q (plan §76)

| # | Scenario | Evidence | Status |
|---|---|---|---|
| A | Generic Git | `test_lifecycle_features` (switch none, zero features), `test_forge_claims` (UNAVAILABLE) | GREEN |
| B | New GitLab project | feature switch to `forge-gitlab` + GitLab provider tests (scripted) | PARTIAL — no live GitLab project exists to qualify |
| C | Legacy GitHub project | V1 projection + migration tests | GREEN |
| D | GitHub → GitLab → none → GitHub | `test_a_round_trip_loses_no_user_data` | GREEN |
| E | Fork origin/upstream ambiguity | resolver + `forge detect` rendering (AMBIGUOUS, exit 0) | GREEN |
| F | Credential exfiltration attack | PR-0A tests (evil URL, artifact URL, gate: zero credentials at non-approved origins) | GREEN |
| G | Private GitHub asset → anonymous CDN | asset API flow test (scripted transport) | GREEN (scripted) |
| H | Tampered ReleaseManifest V3 | `test_release_v3` + `test_lifecycle_update_v3` (zero writes) | GREEN |
| I | Duplicate GitLab package/manifest | provider tests (`RELEASE_DUPLICATE_VERSION`, `RELEASE_MANIFEST_AMBIGUOUS`) | GREEN |
| J | GitLab object-storage blob | shared transport policy test (API → CDN strips credentials); no GitLab-specific 302 fixture yet | PARTIAL |
| K | Claim crash after POST | journal tests (`UNCERTAIN` unresolved, no retry, explicit `abandon`) | GREEN |
| L | Planner refusal during V1 projection | two-work-forge state refuses; projection never writes | GREEN |
| M | Legacy GitLab remote keeps GitHub compatibility default | projection test; the *warning* surfacing is not implemented | PARTIAL |
| N | Read-only V1 projection == persisted V2 | migration parity test + `status` parity test | GREEN |
| O | Missing legacy managed template not resurrected | `test_the_migration_does_not_resurrect_an_absent_template` | GREEN |
| P | Selector conflict identical across commands | one resolver consumed by update/check/status/doctor; conflicts tested at the resolver; no single cross-command E2E test | PARTIAL |
| Q | Mandatory secret patterns survive operator configuration | **not implemented** — the anti-debt scanner contract (`extra_secret_patterns`) is still pending | PENDING |

## Security, migration, claims, integrity

- **Transport:** zero provider credentials observed at non-approved origins
  across the metadata + artifact flow; `https → http` downgrades, userinfo URLs
  and over-long redirect chains refused; `AINATIVE_UPDATE_URL` anonymous.
- **State migration:** V1→V2 inside the next mutation, state-last, idempotent;
  absent managed files stay absent; two-work-forge states refuse.
- **Claims:** journal written durably before the remote signal; corrupt or
  unwritable journals fail closed; an uncertain POST is never retried;
  abandonment is an explicit operator transition that keeps the record.
- **Release integrity:** the manifest is parsed only after its external anchor
  (SHA-256 + size from provider metadata) is verified; the exact version chain
  holds across six identities; enumeration incompleteness and duplicates
  refuse instead of resolving by order.

## Known limitations and remaining work

**P1 — blocks the declared-support gate:**
- GitLab.com live qualification (requires a real GitLab project publishing
  `ai-native-dev-stack` generic packages and an `ainative-release-v3.json`
  manifest).
- Scenario Q: mandatory secret patterns (`MANDATORY_SECRET_PATTERNS` ∪
  operator extras) and the GitLab token-prefix qualification tuple.
- Full CI matrix (Linux/Windows/macOS, py3.11/3.13) — runs on the `dev`
  proposal.
- EN/FR documentation parity automation (plan §75).

**P2 — known gaps, documented rather than hidden:**
- Scenario J: no GitLab-specific object-storage 302 fixture (the shared
  transport policy covers the behavior).
- Scenario M: the "legacy GitLab remote" case projects correctly but no
  warning line is rendered yet.
- Scenario P: no single cross-command selector-conflict E2E test.
- The V2 bridge release and the V3 release have not been published: the plan's
  release choreography (§92) starts after the branch is promoted to `dev`, and
  the first V3 publication stays gated by `V3_BRIDGE_RELEASE`.

**P0:** none known.
