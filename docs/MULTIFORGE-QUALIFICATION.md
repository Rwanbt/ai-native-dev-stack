# Multi-Forge qualification report

**Base commit:** `main` `2674c43` (release v2.5.0) plus the documentation
commits that carry this report. **Architecture:** frozen (Multi-Forge
v1.3.2-final; ADR-0017/0018/0019). **Execution:** local, issue-driven, plus the
full CI matrix on the release SHA itself.

This report states what was verified, with which evidence, and what was not.
Declared support never exceeds qualified support (`SUPPORT.md`, ADR-0019 §13).

## Delivery record

| Step | Where | Evidence |
|---|---|---|
| Multi-Forge v1 promotion | `main` `8f319ad` (PR #176, #173) | architecture frozen, ADR-0017/0018/0019 |
| FIX-A — protocol-aware bridge gate | `main` `f23b59e` (PR #181, #177) | fail-closed gate derives the protocol from the built artifacts; 5 non-vacuity cases + workflow-entry-point mutation test |
| FIX-B/C/D — provider-neutral cleanups | `main` `1d412fd` (PR #182, #178) | reserved `release-api`; declarative `api_version_header`; provider-aware 403/429 hints |
| **Bridge release 2.4.4** | tag `v2.4.4` at `main` `d7b2626` (PR #183, #179) | Release run 35205639491 green; bundle `sha256:d6ddafbd…` (119 928 B), `SHA256SUMS` matches GitHub's digests; bundle attestation verified (exit 0) |
| **V3 release 2.5.0** | tag `v2.5.0` at `main` `2674c43` (PR #184, #180) | Release run 35210583585 green; assets below |
| Manifest attestation fix | `main` `52c05cc` (PR #186, #185) | `subject-path` now covers `dist/*.json`; v2.5.0's gap recorded below, assets never replaced |

Published v2.5.0 assets (GitHub Release, 2026-09-17T10:27:50Z):

| Asset | Size | SHA-256 (== `SHA256SUMS` == GitHub digest) |
|---|---|---|
| `ainative_dev_stack-2.5.0-py3-none-any.whl` | 472 597 | `d2714b532eb226ad24d87e2febb9d61ed2e9c8c6b08c033e03049f145a6aa538` |
| `ainative_dev_stack-2.5.0.tar.gz` | 765 181 | `f7bb94e83c3bd22f3ab9b5d21b50a795674228e21ae7b08db0d13d2b61f66c04` |
| `ainative-lifecycle-v3-2.5.0.zip` | 119 993 | `f801ecdd14b1d1ae03b61de16a5ff8ba1e8c2537e553b79f1825a5831dfb587c` |
| `ainative-release-v3.json` | 502 | `50a4a58f7689fdd137141ac0dbdcdd83f736d9d276149ca9b4129a9cd769a849` |
| `SHA256SUMS` | 395 | `cabf3e24c718d24b282eb39530ae41a47b4c28e9e3abd9672e7c329b3397bf1a` |

No other assets exist on the release — the published set is exactly the
declared set.

## What was delivered

| Stream | Deliverable | Evidence |
|---|---|---|
| PR-0A | Release transport credential confinement (`transport.py`) | 23 tests; characterization probe recorded pre-fix |
| ADR-MF-01/02/03 | ADR-0017/0018/0019 accepted | merged documents |
| PR-0B | V2 forward bridge (`CLI_UPDATE_REQUIRED`) + publication gate | 5 tests; `scripts/check_bridge_release.py` + gate tests |
| PR-1 | Feature model, State V2, atomic switching, GitLab templates | 34 tests + 309-suite regression |
| PR-2 | Work Authority resolver, claim grammar, journal, policy docs, distributed template | 27 tests; policy purity tests |
| PR-3 | `forge detect/status`, doctor extension, status parity | 7 observation tests |
| PR-4 | Source resolver, ReleaseManifest V3, providers, updater wiring | 19 + 32 + 16 + 5 tests |
| PR-5 | GitLab provider (V3 contract), purity tests | 10 provider tests + 7 purity tests |
| FIX-A/B/C/D | Protocol-aware gate, provider-neutral transport/config surfaces | #181/#182 merged, all suites green |
| V3 publisher | Protocol-3 builder + external manifest, anchored chain validation, version 2.5.0 | #184 merged; `check_release_versions.py --tag v2.5.0 --dist` verified the 4 published artifacts pre-upload |

## Platform matrix

| Platform | Status |
|---|---|
| Windows | GREEN — full CI matrix + local suites (315 lifecycle tests, CLI/knowledge/machine suites) |
| Linux | GREEN — full CI matrix on the release SHA `2674c43` |
| macOS | GREEN — full CI matrix on the release SHA `2674c43` |

The full matrix ran on the exact release SHA: 52 jobs green, including
Distribution lifecycle (win/macOS/Linux × py3.11/3.13), Upgrade E2E (three
OSes), Clean-install E2E (three OSes), Installers (three OSes), Verified Work
Plane V2 (Linux/Windows), Multi-Vault suites, Vault v4 protocol, Knowledge B1
and convergence, OpenCode plugin runtime, Python 3.8–3.13, LOC budget gate,
CLI conventions gate and the Production Gate. A separate `sdist round-trip`
workflow was green on the same SHA.

## Forge qualification

| Tuple | Status |
|---|---|
| Generic Git | GREEN — `feature switch none`, zero-feature states valid, observation resolves `UNAVAILABLE` |
| GitHub.com | **GREEN — qualified live for releases and work management (2026-09-17)**: full V3 chain against the published v2.5.0 (enumeration complete; manifest anchor read from the asset API's `digest`+`size` — `50a4a58f…`, 502 B; anchored manifest parsed; exact version chain held; artifact downloaded, 119 993 B, SHA-256 verified against the manifest; lifecycle protocol 3 accepted; payload `VERSION` 2.5.0). Update flows: bridge 2.4.4 sees 2.5.0 with the exact-runtime gate; applying under 2.4.4 refuses `CLI_UPDATE_REQUIRED` with zero writes; the published 2.5.0 CLI applies 2.4.4→2.5.0 through the V3 flow and `update rollback` restores 2.4.4 |
| GitLab.com | **GREEN — qualified live** (2026-09-16) against a public test project (`barat.erwan/ai-native-dev-stack-probe`): Generic Package Registry published `ai-native-dev-stack` 2.4.4 (manifest 514 B `sha256:84a921eb…`, bundle 119 895 B `sha256:67670398…`) plus release `v2.4.4`. Authenticated enumeration (`PRIVATE-TOKEN`), anchor read from the package-file API's `file_sha256` + `size`, anchored manifest parsed, exact version chain held, artifact downloaded with size + SHA-256 verified, lifecycle protocol 3 accepted, and `update check` reported `UPDATE_AVAILABLE 2.4.4` with the exact-runtime gate (`runtime_ready=false` for the 2.4.3 runtime) |
| GitLab Self-Managed | UNTESTED — not supported |
| GitHub Enterprise Server | UNTESTED — not supported |

## E2E scenarios A–Q (plan §76)

| # | Scenario | Evidence | Status |
|---|---|---|---|
| A | Generic Git | `test_lifecycle_features` (switch none, zero features), `test_forge_claims` (UNAVAILABLE) | GREEN |
| B | New GitLab project | live qualification probe (above) + feature switch to `forge-gitlab` | GREEN |
| C | Legacy GitHub project | V1 projection + migration tests | GREEN |
| D | GitHub → GitLab → none → GitHub | `test_a_round_trip_loses_no_user_data` | GREEN |
| E | Fork origin/upstream ambiguity | resolver + `forge detect` rendering (AMBIGUOUS, exit 0) | GREEN |
| F | Credential exfiltration attack | PR-0A tests (evil URL, artifact URL, gate: zero credentials at non-approved origins) | GREEN |
| G | Private GitHub asset → anonymous CDN | asset API flow test (scripted transport) | GREEN (scripted) |
| H | Tampered ReleaseManifest V3 | `test_release_v3` + `test_lifecycle_update_v3` (zero writes) | GREEN |
| I | Duplicate GitLab package/manifest | provider tests (`RELEASE_DUPLICATE_VERSION`, `RELEASE_MANIFEST_AMBIGUOUS`) | GREEN |
| J | GitLab object-storage blob | provider test: the manifest download 302s to an object store; the token is stripped on the blob hop and the bytes arrive | GREEN |
| K | Claim crash after POST | journal tests (`UNCERTAIN` unresolved, no retry, explicit `abandon`) | GREEN |
| L | Planner refusal during V1 projection | two-work-forge state refuses; projection never writes | GREEN |
| M | Legacy GitLab remote keeps GitHub compatibility default | projection test + the doctor warning naming `feature switch forge-gitlab` | GREEN |
| N | Read-only V1 projection == persisted V2 | migration parity test + `status` parity test | GREEN |
| O | Missing legacy managed template not resurrected | `test_the_migration_does_not_resurrect_an_absent_template` | GREEN |
| P | Selector conflict identical across commands | one resolver; a single E2E asserting update check / update / status / doctor all surface `UPDATE_SOURCE_CONFLICT` | GREEN |
| Q | Mandatory secret patterns survive operator configuration | `MANDATORY_SECRET_PATTERNS` (private keys, AWS, GitHub, Slack, GitLab `glpat-`/`gldt-`/`glrt-`/`glsoat-`) with `extra_secret_patterns` as a union; the constructor accepts no replacement parameter; the anti-debt owner and the vault-sync fallback carry the same GitLab prefixes | GREEN |

## Published-release update flows (live evidence)

Executed on Windows against the real releases and real published wheels, in
throw-away git projects, with `GITHUB_TOKEN` from `gh auth token`.

| Flow | Observed |
|---|---|
| Pre-bridge 2.4.3 runtime vs the V3-only 2.5.0 release | `CHECK_FAILED: release publishes no ainative-lifecycle-v2-*.zip lifecycle bundle; the official update path refuses what it cannot verify` — fail-closed, zero writes (2.4.3 predates the bridge; documented manual path applies) |
| Documented manual path: 2.4.3 → bridge 2.4.4 CLI | `pip install --upgrade …@v2.4.4` (the exact published command); the bridge then reports `AI Native 2.5.0 is available … must be applied by runtime 2.5.0` with the upgrade command |
| Bridge 2.4.4 runtime `update` (apply) targeting 2.5.0 | `refused: CLI_UPDATE_REQUIRED`, exit 1, project state untouched |
| Published 2.5.0 CLI applies to a 2.4.4 project | `2.4.4 -> 2.5.0: applied` through the V3 flow; state `2.5.0`, schema 2 |
| `update rollback` | `rolled back to 2.4.4 (1 files)` — project assets only, as stated in the output |
| Fresh install from the published 2.5.0 wheel (no checkout, new venv) | `--version` (lifecycle 2.5.0, schema 2, workplane 0.1.0), `init --profile standard`, `status`, `doctor` (release source resolved, `forge-github` active, work authority `UNAVAILABLE`, 0 unresolved claims), `update check` → `Up to date (2.5.0)`, `feature status`, `forge status` |
| Verified profile install | Bootstrap notice present; `trust show` → `anchor:null, governed:false` — no authority is fabricated |

## Security, migration, claims, integrity

- **Transport:** zero provider credentials observed at non-approved origins
  across the metadata + artifact flow; `https → http` downgrades, userinfo URLs
  and over-long redirect chains refused; `AINATIVE_UPDATE_URL` anonymous.
- **State migration:** V1→V2 inside the next mutation, state-last, idempotent;
  absent managed files stay absent; two-work-forge states refuse; the
  published-release E2E above exercised the live transition (schema 2 after
  both the 2.4.4 and 2.5.0 updates).
- **Claims:** journal written durably before the remote signal; corrupt or
  unwritable journals fail closed; an uncertain POST is never retried;
  abandonment is an explicit operator transition that keeps the record.
- **Release integrity:** the manifest is parsed only after its external anchor
  (SHA-256 + size from provider metadata) is verified; the exact version chain
  holds across six identities; enumeration incompleteness and duplicates
  refuse instead of resolving by order. Verified live on GitHub.com
  (v2.5.0) and GitLab.com (2.4.4).

## Known limitations and remaining work

**v2.5.0 publication — manifest attestation missing (fixed for the next
release, #185):** the release workflow's `subject-path` did not include
`dist/*.json`, so the published `ainative-release-v3.json` of v2.5.0 has no
build-provenance attestation (`gh attestation verify` returns 404 for its
digest). The bundle *is* attested, and the manifest remains covered by
`SHA256SUMS` and by GitHub's asset metadata — which is exactly the anchor the
runtime verifies. The published v2.5.0 assets are **never replaced
retroactively**. The workflow now attests every published asset (`main`
`52c05cc`); the next release must show a verifiable manifest attestation.

**PyPI:** the **Publish to PyPI** workflow is wired (Trusted Publishing/OIDC)
but every run fails because no trusted publisher is registered on the PyPI
account — including the run dispatched for `v2.5.0`. No API-token workaround
is accepted; until the one-time external setup exists, the pinned GitHub
release (now `v2.5.0`) is the supported distribution channel.

**Multi-Vault:** GUARDED, not ENFORCED — the policy and surface exist; no
environment enforces it yet.

**Declared-support gate (P1):** GitLab Self-Managed and GitHub Enterprise
Server remain UNTESTED and are not supported. PyPI publication additionally
depends on the external account configuration above.

**Resolved since the first draft of this report:** the GitLab.com **live**
qualification (scenario B), scenario Q (mandatory secret patterns with
operator extras), scenario J (GitLab object-storage blob), scenario M (legacy
GitLab remote warning), scenario P (one cross-command selector-conflict E2E)
and the EN/FR documentation parity automation
(`tests/purity/test_docs_parity.py`: heading hierarchy, operational surface,
critical security statements — no raw line-count equality). The full CI
matrix now runs on `main` itself, and both releases (2.4.4 bridge, 2.5.0 V3)
are published and verified.

**P0:** none known.
