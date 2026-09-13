# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.4.2] - 2026-09-13

Patch release: the governed Multi-Vault push path now enforces the approved
remote's `allowed_refs`, closing the authorization asymmetry with fetch (#147).

### Fixed

- **Multi-Vault governed push enforces the approved remote's `allowed_refs`**
  (#147): `begin_push()` denies a target ref outside the allowlist, and a
  refspec destination that does not equal the push intent's `target_ref`,
  before any candidate scan or push capability issuance, with the stable code
  `AINATIVE_PUSH_REF_DENIED`.

## [2.4.1] - 2026-09-13

Patch release: the machine ownership record becomes complete and fail-safe.

### Added

- **`existed_before` on every manifest asset** — whether the target existed
  before this stack first wrote it, carried forward by re-runs so a path that
  is now ours is never re-labelled. Pre-existing user content stays
  distinguishable from AI Native content (#20).
- **`machine init --dry-run [--json]` projects the full record** it would
  write, fields included, and writes nothing.

### Changed

- The machine manifest is written beside its target and renamed into place:
  a crash mid-write can no longer truncate it.
- An unreadable manifest now refuses `machine init` too (fail closed, exit 2,
  `MACHINE_MANIFEST_UNREADABLE`), with the exact recovery — installing over a
  corrupt record would have silently destroyed the ownership answers.
- `ainative setup` notes an existing installation before offering a refresh
  and prints next steps after a healthy doctor (#21).

## [2.4.0] - 2026-09-13

Minor release: the machine-wide surface becomes a first-class product, a
guided first run composes the documented steps, and the release pipeline is
qualified end to end. No breaking changes to the documented flow.

### Added

- **`ainative machine`** — `init`, `status`, `doctor`, `repair` and
  `uninstall` over the canonical `~/.ai-native/machine.json` manifest
  (schema 2). Installation records what it wrote (links with their source,
  blocks with their heading or vault pair, rendered files with template and
  digest); `status` classifies every asset (OK / MISSING / MODIFIED / DRIFTED /
  MALFORMED); `doctor` exits non-zero on any problem; `repair` re-creates
  only what the manifest proves — a user-modified file, a retargeted link or a
  malformed block is preserved and reported, never overwritten; `uninstall`
  removes only recorded, unmodified assets. A corrupt manifest fails closed
  (exit 2, zero writes), and schema-1 manifests stay readable.
- **`ainative setup`** — the guided first run: it detects the harnesses,
  explains Standard vs Verified, offers the project install, offers the
  machine-wide integration, reports the optional vault and Graphify, and
  finishes with the same doctor every other command runs. Every step asks
  before it mutates and is skippable; `--non-interactive` (or `--json`) takes
  its choices from `--profile` and `--machine`, so CI and scripts never block.
- **The machine installer is packaged.** The ownership rules, managed blocks
  and the manifest write now live in `ainative.lifecycle.machine` /
  `machine_install` / `machine_health`; `scripts/install_agents.py` and
  `scripts/machine_lifecycle.py` are thin frontends over the same code, so a
  checkout and the installed CLI cannot drift apart. The payload lacking an
  asset (the anti-debt agent, the adapter files) is skipped with a visible
  `SKIP`, never turned into a broken link.

### Changed

- **CI blocking is one gate.** `Production Gate` is the single aggregate job
  the branch protection requires: it needs every blocking job in `ci.yml` and
  fails on `failure`, `cancelled`, an unexpected `skipped`, or a job missing
  from its payload (`tests/test_ci_production_gate.py` proves each case — a
  new job cannot silently stay outside the gate). Python 3.8 moves to its own
  best-effort job, deliberately outside the gate, matching the documented
  contract.
- **The colleague run is a gate.** `scripts/colleague_e2e.py` builds the wheel,
  installs it in a fresh venv, and executes the README literally — init,
  status, doctor, knowledge, context, the template, `generate_all`, an edit
  through the configured PostToolUse command, `update check`, `uninstall
  --dry-run`. It caught real defects while being written; it now runs on every
  PR (`colleague-e2e`).

### Fixed

- `ainative doctor` no longer crashes when the environment check reports a
  non-OK status after project installs (found by the colleague run on a fresh
  wheel).
- `UPDATING.md` and both READMEs name the current pinned release and the v2
  protocol bundle; the old manual hook-registration step is replaced by the
  commands that configure it.

## [2.3.0] - 2026-09-13

Minor release: the product surface grows (Verified onboarding, machine
lifecycle, whole-stack diagnostics, a versioned update protocol) without
breaking the documented Standard flow. A stranger can now install, initialize,
diagnose, update, roll back and uninstall — and a Verified user can scaffold and
bootstrap trust — without reading the source.

### Added

- **Verified onboarding.** `ainative trust init` writes a minimal approval-root
  and policy scaffold (validated by the same code bootstrap uses, claiming no
  authority); `ainative trust bootstrap` stays the explicit ceremony. One
  schema owner (`trust_schema.py`) validates both documents before anything
  reads them. `scripts/verified_first_run_e2e.py` drives the whole governed
  workflow — init, trust init, bootstrap, work admit/new, verify, converge to
  CONVERGED — from a fresh wheel and venv, on Linux, Windows and macOS.
- **The hook is configured by `init`.** A new `claude-hook` component merges
  exactly one owned `PostToolUse` entry into `.claude/settings.json`:
  user keys and hook groups are preserved, a re-init never duplicates it,
  uninstall/rollback remove only the owned entry, and an unparsable file is
  refused rather than rewritten.
- **Whole-stack `doctor`.** Beside the lifecycle diagnosis it now reports the
  Python, Git (repository/HEAD/state), Node, the harness hook, harness
  integration, the vault and its REST API when configured, Graphify, the
  machine manifest and the Trust anchor — each as OK / ABSENT_OPTIONAL /
  DEGRADED / FAIL with its impact. Missing automation fails; optional tools do
  not.
- **Machine lifecycle.** Every global install records
  `~/.ai-native/machine.json` (source or digest per asset), and
  `scripts/install_agents.py --uninstall [--dry-run]` reverses exactly that
  record: user files and user-modified assets are preserved, file ownership is
  provable, and the manifest is removed only after success.
- **Versioned update protocol v2.** Bundles are now
  `ainative-lifecycle-v2-<version>.zip` (protocol document + payload under
  `stack/`). Runtimes up to v2.2.2 cannot consume such a bundle even from a
  mirror — the layout refuses them. v2.2.2 refuses at the runtime gate before
  downloading. The documented path is unchanged: upgrade the CLI first.
- **Authenticated update checks.** `GITHUB_TOKEN`/`GH_TOKEN` is sent as a
  bearer header when present (never logged, never cached); 403/429 answers are
  reported as a rate-limit diagnosis with the remedy.
  `ainative update check --strict` exits non-zero when the source could not be
  consulted — the default still exits 0, because the answer is what it is.
- **Atomic, attested releases.** The release workflow builds everything, gates
  every artifact, attests build provenance
  (`gh attestation verify <file> -R Rwanbt/ai-native-dev-stack`), creates the
  release as a draft, uploads without `--clobber`, verifies the published
  names/sizes/digests, and only then publishes. A new `publish-pypi.yml`
  publishes the wheel and sdist through PyPI Trusted Publishing (OIDC); the
  one-time PyPI setup is documented in `docs/RELEASING.md`.
- **Machine-path gate.** `scripts/check_personal_paths.py` refuses any tracked
  file carrying a user profile, home directory or the maintainer's account in a
  path, with a reasoned allowlist for historical evidence; the mutation test
  proves it blocks.
- **Docs for strangers.** `SUPPORT.md` (what is supported, how to report, known
  limitations), `CODE_OF_CONDUCT.md`, and `docs/RELEASING.md`.

### Changed

- **Non-Git projects.** Standard installs with an explicit notice and a
  DEGRADED doctor report (Knowledge persistence and provenance need a
  repository); Verified refuses with `GIT_REPOSITORY_REQUIRED`.
- **Truthful plan vocabulary.** `BLOCK_WRITE`/`BLOCK_REMOVE` (which read as
  "blocked" while the operation proceeded) are replaced by
  `REGION_WRITE`/`REGION_REMOVE` and `HOOK_WRITE`/`HOOK_REMOVE`; older journals
  remain readable.
- **Knowledge works on a fresh install (#138).** The managed `.gitignore`
  region now carries `.ai-native/state/`, and refusals print the exact remedy.
  Knowledge state and the trust anchor are owner-only on POSIX.
- `lifecycle_dogfood.py` runs again (#137) and immediately caught a stale
  non-vacuity anchor, fixed here.

### Fixed

- **No more tracebacks for invalid trusted input.** `ainative trust bootstrap`
  with `{}` raised `KeyError` and exited 1 (the NOT_CONVERGED code). Validation
  now precedes use; refusals print a stable code on stderr and the same record
  as JSON on stdout, always exit 2.
- Machine-specific paths removed from distributed files: the committed
  Mavis-generated OpenCode artifacts are gone, the enforcement script carries no
  personal defaults, and the maintainer's email left the fixtures.
- `rendered_file` writes bytes, so a recorded digest matches the file on
  Windows; the machine uninstall's dry run is pure (it no longer classifies by
  mutating).


## [2.2.2] - 2026-09-13

Corrective release closing the post-v2.2.1 audit. Two architectural
invariants replace previously implicit behaviour: a release's version labels
now form one fail-closed chain from git tag to installed project, and a
lifecycle runtime that differs from the target release can no longer apply it.

### Fixed

- **Release version chain (AUD-201).** A tag `v2.2.2` could promote a tree
  whose `VERSION` said 2.2.1, and the published bundle's internal `VERSION`
  was never compared against the release it came from. The release workflow
  now refuses `tag != v$(cat VERSION)` and re-checks every built artifact
  (bundle filename and internal `VERSION`, wheel filename and `METADATA`,
  sdist filename and `PKG-INFO`) through the reusable
  `scripts/check_release_versions.py` gate. The official provider accepts only
  `ainative-dev-stack-<release.version>.zip` - a release publishing another
  version's bundle is refused with the new stable code
  `UPDATE_VERSION_MISMATCH`, before any download; the local mirror index obeys
  the same rule. The updater also refuses a bundle whose internal `VERSION`
  differs from the release it declared, before any project write.
- **Runtime freshness (AUD-202, #131).** `ainative update` now requires the
  installed lifecycle runtime to be exactly the target release version. A
  mismatch is refused with the new stable code `CLI_UPDATE_REQUIRED` - before
  the archive is downloaded and before the first write, with the upgrade
  command in the message and in the JSON `detail`. `update check`,
  `status --check-updates` and `doctor --check-updates` still report what is
  available and now say when the CLI must be upgraded first.
- **Stale update cache (#131).** After a successful update, the cached
  availability notice could still announce the version the project had just
  moved to (`2.2.1 is available. Current: 2.2.1`) until the TTL expired. Every
  read of the cache now compares the cached `latest` against the live project
  version: a notice that is not newer resolves to `UP_TO_DATE`, a malformed
  cached version resolves fail-safe, and the cache is never rewritten by a
  read-only command.
- **Rollback dry-run wording (#131).** `ainative update rollback --dry-run`
  printed "rolled back to ..." while writing nothing. It now prints
  "(dry-run - nothing was written)" and "would roll back to ...", keeps
  `"dry_run": true` in JSON, and a test captures stdout to pin both.
- **Anti-debt secret previews (AUD-203).** trufflehog and gitleaks findings no
  longer persist the first 8 characters of a detected secret in the id or the
  evidence; they carry a non-reversible `sha256(secret)[:12]` fingerprint,
  stable for the same input and distinct across secrets.
- **Anti-debt failure boundary.** A defect in a scanner's own parser
  (`AttributeError`, `TypeError`, `NameError` - the class of the clippy
  `line_start` bug of #127) is no longer converted into a `{"warning": ...}`
  entry; it fails the scan visibly. Missing binaries, timeouts, non-zero exits
  and invalid external JSON still degrade to structured warnings.

### Added

- Release gate script `scripts/check_release_versions.py`, run before and
  after the release build: `TAG == VERSION == ainative.__version__ ==
  wheel/sdist/bundle labels == bundle internal VERSION`.
- Upgrade E2E `scripts/lifecycle_upgrade_e2e.py` and its CI job: two real
  wheels are built, one installed into a fresh venv, and the console script
  crosses the transition for real - old runtime refuses (`CLI_UPDATE_REQUIRED`,
  zero writes), runtime upgraded, update applies, rollback restores, tampered
  bundle refuses (`UPDATE_INTEGRITY_FAILED`, zero writes).
- Version-chain and stale-cache test suites, including mutation cases for
  tag/asset/internal-VERSION mismatches and zero-write assertions; the
  lifecycle non-vacuity suite proves each new guard actually blocks.
- Supply-chain baseline (#129): all GitHub Actions pinned to commit SHAs,
  `.github/dependabot.yml` (github-actions), a real `SECURITY.md` reporting
  path, and `.github/CODEOWNERS` for the sensitive zones.

### Changed

- Historical Knowledge documents (`docs/K0-A-CAPABILITIES.md` flagged, K0-B
  index annotated) now point at `docs/knowledge/KNOWLEDGE-CONVERGENCE-MATRIX.md`
  as the current state instead of reading as current capability claims.
- CI: the Python 3.8 matrix entry's `continue-on-error` is actually wired
  (best-effort documented surface); the orphan `tests/mv00` Multi-Vault
  feasibility suites now run; `docs/AI_CONTEXT` for the anti-debt scanners
  describes the real `shell=False` execution model of #127.


## [2.2.1] - 2026-09-13

Corrective release. v2.2.0 is rolled back on `main` by revert (`b0c7ffd`,
reverting `fc0a270`); its tag and published release remain untouched as the
historical record of what was distributed. Everything below is the corrective
fix set, qualified by a published-artifact E2E before the tag.

### Fixed

- **Version source of truth (#125).** `VERSION` declared `2.0.0` while
  `ainative.__version__` declared `2.2.0`, and the lifecycle records the
  `VERSION` file - so a fresh install disagreed with the release it came from.
  `VERSION`, the package version, the `AGENTS.md` `stack-version` header, the
  staged payload, the wheel payload and the release bundle now move together,
  and the build refuses a tree carrying two versions.
- **Official update integrity (#126).** The updater fell back to the GitHub
  `zipball_url` with no digest to compare. The official path now consumes only
  the published lifecycle bundle `ainative-dev-stack-<version>.zip`, requires
  its published SHA-256, and fails closed with
  `UPDATE_INTEGRITY_METADATA_MISSING` when the metadata is missing (no bundle,
  no digest, malformed digest). `verify_archive` refuses a missing digest
  outright; the `releases.json` mirror obeys the same contract.
- **Anti-Debt scanner execution (#127).** Scanners run from native argument
  vectors with `shell=False` (documented `cmd /c` routing for Windows `.cmd`
  shims); the clippy parser reads the integer `line_start` instead of treating
  it as a mapping, so clippy findings are normalized instead of silently
  degrading to a warning.
- **Complexity budget source (#39).** `check_complexity_budget.py` reads
  `cyclomatic_complexity.blocking` from `conventions.json` instead of
  re-declaring the number; a missing or malformed budget refuses the check.

### Added

- Lifecycle bundle `ainative-dev-stack-<version>.zip` published with every
  release beside the wheel, the sdist and `SHA256SUMS`.
- Release workflow hardening: the tag must equal the current `main`, and
  assets are never silently replaced (no `--clobber`).
- CI coverage: the 14 root test suites no workflow executed now run
  (new `knowledge-b2` job plus explicit steps; #53).
- Version-invariant tests (checkout, staged payload, lifecycle bundle, wheel
  payload and metadata, `AGENTS.md` header) and official-update integrity
  tests (release-shaped document, flipped-byte refusal with zero project
  writes, missing-digest refusal, zipball-only refusal, full update
  transaction with rollback available).

### Changed

- `_payload_staging.py` owns payload staging and the version-consistency gate,
  shared by the PEP 517 backend and `scripts/build_lifecycle_bundle.py`.


## [2.2.0] - 2026-09-12

### Added

- **Knowledge / Auto-Memory convergence** on the current architecture (K1-K4 owners;
  legacy parity 18/18 - 13 PORTED, 2 SUPERSEDED, 3 INTENTIONALLY DROPPED, no UNKNOWN):
  - advisory classifier, cross-harness import (preview/apply, identity via the current
    grammar, secret quarantine), owner-composed maintenance (dry-run default), dependency
    staleness with ranking-only decay, advisory consolidation, review queue and conflicts
    surface, and the full bounded working-memory fields in `continuity.py`;
  - `ainative context checkpoint|save|restore|status|clear` (working continuity CLI);
  - `ainative doctor` gains an honest Knowledge section (ABSENT/OK/FAIL, providers
    ABSENT = degraded, promotion GATE_CLOSED, trust UNVERIFIED);
  - thin session hooks (SessionStart restore/status, PreCompact checkpoint, SessionEnd
    checkpoint + advisory consolidation, PostEdit staleness) that shell out to the CLI.

- Behavioural E2E A-J for the whole system (restart persistence, dedup, conflict without
  auto-resolution, checkpoint/restore, divergence surfacing, secret quarantine with zero
  persistence, deterministic context without recall providers, isolation, staleness
  without rewrite, advisory-only consolidation) and knowledge isolation E2E (cross-project
  refusal, ambient-environment immunity, universal approval-gate closure).

### Fixed

- `python -m ainative` module entry point added (hook robustness).

### Notes

- **K5 = STOP**: canonical auto-promotion is intentionally not shipped. The measurement
  gate (docs/knowledge/K1-K4-MEASUREMENT-GATE.md) documents the decision: K1-K4 are
  correct and fail-closed, but benefit metrics require a real usage window before any
  NARROW proposal. Promotion is GATE_CLOSED; trust is UNVERIFIED under the standard
  operator ceremony. This is a measured decision, not missing debt.

## [2.1.1] - 2026-09-12

### Fixed

- `python -m build` round-trip: `MANIFEST.in` ships the in-tree build backend and
  the payload sources, so a wheel built from the generated sdist works without the
  checkout (#54).
- Current qualification evidence references the exact published release SHA
  `a55ac69` / CI run 34685643192 / tag `v2.1.0` (the matrix and report no longer
  diverge from the release).

### Changed

- User-facing documentation: removed the contradictory historical verdicts from the
  Multi-Vault operator guide, made the migration guide CLI-first, and added
  Multi-Vault sections to README EN and FR with a pinned reproducible Quick Start.

### Added

- Dedicated CI gates: a build-from-sdist round-trip workflow (build, wheel from
  sdist, fresh-venv install, `ainative --version`, `init --dry-run`) and a release
  workflow that publishes wheel, sdist and `SHA256SUMS` as release assets.

## [2.1.0] - 2026-09-12

### Added

- **Multi-Vault GUARDED production readiness**: profiles A/B/C/D GUARDED QUALIFIED;
  `ainative multivault bind|doctor|context|exec|sync`; governed Git transfers through
  the transfer engine only; clean-install wheel E2E; real canary sweep (exit 0);
  fault-injection matrix; qualification evidence under
  `docs/spikes/multivault/` and `docs/qualification/`.
### Added

- GitHub-centered work management: `docs/GITHUB-WORKFLOW.md` defines Issue /
  Project / ADR / Work Contract / Vault responsibilities, MERGE_READY vs DONE,
  Refs-vs-Closes, deterministic multi-agent claims and review scope; root
  `AGENTS.md` carries the always-on policy, `CONTRIBUTING.md` the contributor
  flow.
- Skills: `skills/github-triage` (findings to clean backlog entries, with
  duplicate detection and P3 research discipline) and
  `skills/issue-to-implementation` (claimed Issue to merged PR with
  Acceptance-Criteria protection and FINAL_MERGE_FRESHNESS), plus stdlib-only
  helpers `bin/claim_resolution.py` and `bin/ac_guard.py` with their decision
  tables pinned by tests.
- Generic contribution templates shipped as managed files
  (`templates/github/`, installed via the new `github-templates` component):
  bug and feature issue templates plus a PR template that starts with
  `Refs #` and deliberately contains no `Closes`.
- Managed-template ownership safety, made executable by
  `tests/test_lifecycle_github_templates.py`: pre-existing user templates are
  preserved and reported, user-modified managed templates are preserved as
  conflicts, unchanged managed templates stay idempotent and updatable, and
  `--dry-run` never touches the filesystem.
- **Implementation Economy architecture** — accepted ADR-0010 defines an
  ownership-first implementation discipline for minimizing accidental
  complexity while preserving accepted scope, engineering invariants,
  fail-closed deletion safety and Verified Work Plane authority.
- **Implementation Economy skill** `skills/implementation-economy` ships the
  ownership-first procedure (STOP applicability barrier, ownership-first
  selection, residual Novelty Gate, fail-closed deletion) with contract tests;
  the existing generic installer mechanism exposes it with every other skill.

## [2.0.0] - 2026-09-05

This release ships
the **Distribution & Lifecycle Manager** (Standard and Verified profiles,
recorded file ownership, transactional install / update / uninstall) and the
**Verified Work Plane V2**. The stack release version is 2.0.0; the Work Plane
runtime version and the lifecycle state-schema version are independent numbers
(see `docs/DISTRIBUTION-LIFECYCLE.md`, section 13).

### Added

#### Distribution & Lifecycle Manager

- **Two profiles, `standard` and `verified`**, declared in
  `ainative/lifecycle/data/profiles.json`. `verified` extends `standard` and
  lists only what it adds; the resolver computes the effective component set.
  The dependency runs one way — the lifecycle layer may invoke the Verified
  Work Plane, never the reverse, and installing Standard loads no authority
  module. Proved by inspecting `sys.modules`, not by convention.
- **`ainative` as a top-level dispatcher** — `init`, `profile status|switch|purge`,
  `status`, `doctor`, `repair`, `uninstall`, `update check|apply|rollback`, plus
  the unchanged Verified surface (`trust`, `work`, `verify`, `converge`,
  `debug`), handed over verbatim with their own exit codes.
- **Recorded file ownership.** Four classes (`MANAGED_IMMUTABLE`,
  `MANAGED_MUTABLE`, `USER_DATA`, `EXTERNAL_CONFIG`) and a SHA-256 per managed
  file taken at the moment the stack writes it. This is what makes uninstall and
  update possible at all: a file the stack wrote is now distinguishable from a
  file the user rewrote.
- **Transactional mutations** — backup, apply, verify, then commit the install
  state *last*, with a journal at `.ai-native/lifecycle/transactions/`. An
  interruption leaves the old valid state or the new one; `ainative repair`
  completes the rollback. An `O_EXCL` lock with liveness-checked stale detection
  keeps two mutations from interleaving.
- **Non-destructive downgrade.** `profile switch standard` deactivates Verified
  governance and preserves `.ai-native/{trust,work,runs}` as dormant state.
  Deleting it is a separate, explicit `ainative profile purge verified`.
- **Update lifecycle** — cached detection (24 h TTL, bounded timeout, `OFFLINE`
  is not fatal), transactional application with archive digest and path-safety
  verification, `.new` files instead of merges for user-modified content, and
  `ainative update rollback` for the project's assets. Detection is automatic;
  application never is, and no authority command ever reaches the network.
- **Legacy adoption.** A project installed before the lifecycle existed is
  detected and adopted on the next `init`. A file is claimed only when its bytes
  match what the distribution ships; anything else is tracked but never replaced
  and never removed.
- `--dry-run` on every mutation, `--yes` on every confirmation, `--json` on
  every command a script would parse, and stable exit codes (0/1/2/3).
- `docs/DISTRIBUTION-LIFECYCLE.md` and
  [ADR-0009](docs/adr/0009-distribution-profiles-and-lifecycle-ownership.md).
- `scripts/lifecycle_non_vacuity.py` — reverts each guard in a scratch copy and
  requires the matching test to fail. Three cases were reported VACUOUS on the
  first run and were real: two guards were layered so removing one proved
  nothing, and one test could not see commit ordering at all.
- `scripts/lifecycle_clean_install.py` + a CI job on all three OSes — builds the
  wheel, installs it into a throwaway venv, and drives the console script from a
  directory with no `PYTHONPATH` and no checkout, asserting that the staged
  payload installs exactly what a checkout installs.
- An in-tree PEP 517 backend (`_build_backend.py`) that stages the installable
  payload into the wheel, so the repository keeps one copy of its own method and
  a user with no checkout can still install a profile.

- `conventions.json` — machine-readable twin of the size/complexity thresholds
  declared in `AGENTS.md`. Every enforcement point now reads it instead of
  carrying its own copy of the numbers.
- `scripts/validate_conventions.py` + a CI job — fails the build when
  `AGENTS.md` and `conventions.json` disagree on any threshold.
- `install.py` / `install.ps1` — cross-platform per-project installer.
  `install.sh` is now a thin shim that locates Python and delegates.
- `scripts/setup-agents.ps1` — Windows-native entry point for the global
  installer; Git Bash and WSL are no longer required on Windows.
- C/C++ scanner in `polyglot_scan.py` — function-level cyclomatic complexity,
  length and god-function detection, with comment- and string-aware parsing.
  C/C++ was previously the only major language the debt scanners ignored.
- `hooks/lib/obsidian_client.js` — one Obsidian REST client shared by the two
  memory hooks, which each carried a diverging copy.
- `skills/ai-pilot/` — the AI-pilotability pattern skill, scrubbed of personal
  paths and private project references.
- CI now exercises both installers on Linux, macOS and Windows (dry-run, real
  install, idempotent re-run, `--check`), and both memory hooks on all three.
- `scripts/vault_sync.py` + `vault_sync_once_daily.py` — cross-platform Obsidian
  vault sync replacing the committed PowerShell placeholder, with `.ps1`/`.sh`
  shims. Verifies the push by re-reading the remote ref, refuses a non-primary
  branch, stops on divergence, scans staged content for credentials, and locks
  inside `.git/`. Covered by a CI job on Linux and Windows.
- `scripts/measure_scope.py` + a CI job — re-measures the repository and fails
  when `AGENTS.md`'s scope table drifts from reality.
- `skills/commit-convention/` — Conventional Commits 1.0 enforcer with two
  complementary modes:
  - **Auto-suggest** — when the user says "commit", `/commit`, or has a
    non-empty staged diff and seems ready to commit, the skill inspects
    `git diff --staged`, infers type/scope/subject, and proposes 1–3
    candidates via AskUserQuestion.
  - **Validator hook** — `bin/validate-commit.sh` (PreToolUse on `Bash`)
    validates every `git commit` first line against the CC regex. PASS is
    silent `allow`; non-conformant or soft-warning commits (full line > 100
    chars, trailing period, BREAKING CHANGE without `!`) trigger `ask` with
    a `[warn]` prefix. `--no-verify` is honored as a user override.
  - 18 zero-dependency smoke tests (`tests/test_validate.sh`) cover allow /
    ask / warn paths and pass green.
- `install.sh` copies `commit-convention` into `.claude/skills/` of the target
  project, alongside the existing `verify-ai-docs` and `verify-standards`.

### Fixed

- **LOC gate warnings never reached the agent.** The 500 and 800 LOC branches
  built a `reason` string and then emitted a payload that did not contain it,
  so only the 1500 blocking tier had any visible effect. Warnings now carry
  `reason` like the blocking tier does.
- **Convention thresholds were enforced at values `AGENTS.md` never declared.**
  Cyclomatic complexity `>25 blocking` was implemented as `20`, the `>15 alert`
  tier did not exist, and function size `>200 blocking` was not implemented at
  all. All three ladders now come from `conventions.json` and are CI-verified.
- **`session-end-save` could truncate `LOG.md`.** It read the log, concatenated
  and PUT the whole file back; a failed read was indistinguishable from an
  empty file, so a read failure rewrote the log with a single entry. It now
  appends, which also removes the lost-update race between concurrent sessions.
- **`session-end-save` ignored `OBSIDIAN_API_URL` on write** — the URL was
  computed and then discarded in favour of a hardcoded host and port.
- **Both memory hooks failed silently.** Every error path resolved to an empty
  string, so an unreachable vault looked like a successful empty load. They now
  report the failure and the endpoints they tried.
- Memory hooks now try the plugin's default HTTPS endpoint (`27124`) before the
  non-encrypted `27123`, which the plugin ships disabled.
- **`install.sh` installed skills only into `.claude/skills/`**, so on OpenCode
  or Codex they landed where the CLI never looks. The installer now writes to
  every known agent root, and discovers skills from `skills/*/SKILL.md` instead
  of a hardcoded list that silently went stale.
- `install_agents.py` reported its own Windows junctions as unmanaged paths,
  making `--check` fail on every Windows install it had performed.
- `verify-ai-docs` TIER 9 only looked at `.claude/skills`, reporting "no
  skills" on projects driven by another CLI.
- OpenCode plugin adapter no longer hardcodes the LOC threshold (it reads
  `conventions.json` at runtime) and no longer assumes `python3` exists, which
  is false on a default Windows install.
- **`AGENTS.md` misdescribed this repository by an order of magnitude.** Its
  scope table claimed 11 files and ~22 000 tokens, measured ten weeks and 178
  files earlier, and told every agent to "direct read always" a repo that is
  now ~231 000 tokens. Corrected, split by scope, and guarded by CI.
- **The vault sync reported successes it never performed.** It pushed a
  hardcoded `master` rather than the checked-out branch and printed
  "pushed to GitHub (N commits)" without verifying anything; the once-daily
  wrapper then recorded the day as done. See Added above.
- `install.py` copied skill trees without pruning, so a file removed upstream
  stayed in every project that had installed it earlier.
- The LOC gate applied to any file handed to it, so a long CHANGELOG or dataset
  blocked an edit. Single-file mode now honours `scan_extensions` and reports
  the skip rather than staying silent.
- `README.fr.md` still documented the pre-cross-platform install; it now
  mirrors `README.md`.

### Changed

- **One authority for the lifecycle.** `install.py` is now a bootstrap for the
  one situation `pip` cannot cover — a fresh machine — and delegates to
  `ainative init`; `install.sh` and `install.ps1` find a Python and hand over.
  Its pre-lifecycle flags (`--project-root`, `--skip-gstack`, `--with-gstack`,
  `--gstack-ref`, `--dry-run`) still work.
- **`install.py` no longer prunes a file it did not write.** `copy_tree` deleted
  anything under a managed directory that the source no longer had, including a
  skill the user had edited. Pruning is now decided per file by the digest
  recorded at install time.
- `scripts/stack-update-check.sh` and `scripts/stack-upgrade.sh` are documented
  as what they are — *clone*-level operations. The project-level update is
  `ainative update`. There is no second project updater.
- The console entry point moved from `ainative_workplane.cli:main` to
  `ainative.cli:main`, which dispatches. Every Verified command keeps its
  grammar, output and exit codes.
- The distribution is now `ainative-dev-stack` and ships both packages; the
  lifecycle CLI requires Python 3.11+ (the AI-docs tooling it installs still
  runs on 3.8+). `docs/DISTRIBUTION-LIFECYCLE.md` states the three surfaces.
- `scripts/check_complexity_budget.py` measures the lifecycle package too, and
  the CI LOC gate covers `ainative/`.
- **One implementation of the LOC rule.** `scripts/loc_gate.ps1` is merged into
  `hooks/pretool-loc-gate/run_gate.js`, which now offers all three modes
  (single file, `--staged`, `--all`). The CI job calls that same script, so CI
  and the hook can no longer disagree about the limit.
- `scripts/install-linux.py` → `scripts/install_agents.py`, no longer gated to
  Linux; `setup-agents.sh` is a shim over it on every platform.
- The Rust and JS scanners now share one size/complexity ladder and one secret
  sweep instead of re-implementing both.
- gstack is no longer installed by a 15-second prompt that defaulted to *yes*
  when unattended. It is opt-in (`--with-gstack`), can be pinned
  (`--gstack-ref`), and the resolved commit is recorded in `.stack-lock.json`.

### Removed

- `scripts/loc_gate.ps1` — merged into `run_gate.js` (recoverable via
  `git log -S`).

### Security / Safety

- **Recorded ownership.** Every managed file carries the SHA-256 it had when
  the stack wrote it; a file the user edited is never replaced and never
  removed — not by an update, an uninstall, or `--purge`.
- **Transactional mutations.** Backup first, install state committed last,
  journaled, and recoverable with `ainative repair` — no half-installed state.
- **Path safety.** Manifest destinations and every archive entry are validated
  against traversal (`../../etc/cron.d/x` is refused); archive entry count and
  expanded size are bounded.
- **Detection is automatic; application never is.** Updates are never applied
  without an explicit command, and the authority commands (`verify`,
  `converge`, `trust`, `work`) never touch the network.
- **Trust bootstrap stays human.** `ainative init --profile verified` prepares
  the environment but never manufactures the trust anchor (ADR-0006).
- **Integrity boundary, stated precisely.** SHA-256 protects against a
  corrupted or substituted archive in transit; it does not protect against a
  compromised release source. Release signing is not implemented and not
  claimed — tracked as a signed-releases issue on the security roadmap.

### Known limitations

- Machine-wide harness integration (global hooks, cross-CLI skill links, Vault
  governance blocks, the OpenCode plugin) is installed separately by
  `scripts/install_agents.py` — `ainative init` configures the project only.
- The lifecycle CLI requires Python 3.11+; the AI-docs tooling it installs
  still runs on 3.8+.
- Verified Work Plane genesis trust is inside the TCB: bootstrap trust before
  a controlled agent has repository access (ADR-0006; deployment requirement).
- There is no machine-level lifecycle yet (`ainative machine …`): global
  install, status and removal remain `scripts/install_agents.py` operations.

## [1.0.0] - 2026-06-19

First tagged release. The stack now spans four cooperating layers — the
**AI-docs maintenance system**, the **canonical engineering method**, the
**universal hooks**, and the **anti-debt governance agent** — all transferable
across machines/LLMs and updated non-destructively.

### Added

#### Engineering method & portability
- `AGENTS.md` — the **single canonical source** of the engineering method: the
  always-on core rules plus the full senior-reflexes playbook (ADR/RFC,
  sanitizers+Miri, FFI conventions, lock hierarchy, RT lock-free telemetry,
  fuzz/property tests, CODEOWNERS, supply-chain scans, perf budgets, debt SLA,
  Boy Scout…) and the codebase-analysis/routing strategy. Tool configs *reference*
  it (`@AGENTS.md`) instead of copying, so they never diverge.
- `PORTABILITY.md` — multi-agent transfer guide: the 3-layer model (method /
  tool-mechanics / personal), new-machine bootstrap, per-agent setup for Claude
  Code, MiniMax/Mavis, Cursor and Codex, and an in-repo vs machine-local matrix.
- `scripts/setup-agents.sh` — idempotent, OS-aware linker (symlink on Linux/macOS,
  junction on Windows) that wires the anti-debt agent into every detected agent root.
- `routing-guide.md` — universal port of the subagent-vs-direct-read routing rule.

#### Non-destructive updates (gstack-style)
- `VERSION` (semver) + `stack-version` header in `AGENTS.md` — version source of truth.
- `scripts/stack-update-check.sh` — read-only upstream-update detection (fetch + compare).
- `scripts/stack-upgrade.sh` — non-destructive, fast-forward-only upgrade; aborts on a
  dirty tree, touches only the shared repo, reports changed `*.example` templates.
- `skills/stack-upgrade/SKILL.md` — the `/stack-upgrade` command.
- `scripts/sync_inlined_method.py` — regenerates a `STACK:BEGIN/END` managed block
  from `AGENTS.md` (with `--check` for CI), for agents without an `@file` import
  (e.g. MiniMax/Mavis): the method is inlined and re-synced, never hand-forked.
- `UPDATING.md` — the non-destructive update model ("reference, don't copy") + the
  managed-block convention.

#### Universal hooks
- `hooks/` — six cross-agent hooks (session-start memory, session-end save,
  PostToolUse AI summary, PreToolUse LOC gate, graphify inject, readonly-env
  permission) with per-hook install notes. The Obsidian key is read from the
  `OBSIDIAN_API_KEY` environment variable (never committed).
- `scripts/loc_gate.ps1`, `scripts/vault_sync*.ps1` — quality/vault helpers.

#### Anti-debt governance agent (`stack/agents/anti-debt/`)
- LLM-agnostic technical-debt governance: deterministic scanners + Critic Engine
  (confidence tiers reject&lt;0.6 / review&lt;0.7 / accept) + SQLite Knowledge Graph
  + governance skills, with adapters for Claude Code / MiniMax / generic.
- Deterministic finding identity (`finding_id`, sha256 — stable across scans, so
  dedup/KG/history/calibration work), schema-conformant findings, deterministic
  triage separated from LLM remediation plans, centralized secret patterns, and
  25 ADRs (incl. ADR-0025 calibration semantics + CC parser exceptions).

#### AI-docs maintenance system
- `tools/ai_docs/source_config.py` — single source of truth for source extensions;
  also exports `EXCLUDE_DIRS`, the unified directory-exclusion set shared by all tools.
- `tools/ai_docs/module_discovery.py` — shared `find_module()`, eliminating the
  divergent str-vs-Path duplicate between `update_on_edit.py` and `assemble_context.py`.
- `tools/ai_docs/generate_metrics.py` — objective, git-derived stack metrics written
  to `docs/METRICS.md` (coverage, freshness, drift, KFP/ADR counts, risk zones, trend).
- `parse_fsharp()` — best-effort F# parser; `.fs`/`.fsi` no longer routed to `parse_csharp()`.
- `tools/ai_docs/tests/` — 38-test zero-dependency `unittest` suite.
- `.github/workflows/ci.yml` — tests on Python 3.8/3.9/3.11/3.13 + a 1500-LOC budget gate.
- `.gitattributes` (forces LF), `CONTRIBUTING.md`, `PYTHON_BIN` config option.
- Documented the flat-module constraint in `README.md`, `CONTRIBUTING.md`, and
  `AI_CONTEXT_template.md`; `settings_hook_example.json` setup notes.

### Fixed
- `install.sh` did not copy `generate_metrics.py` (metrics broken on fresh install).
- `generate_metrics.py` listed file names in `SKIP_DIRS`, pinning module coverage to 0%;
  it now also normalises Windows backslashes before passing paths to git.
- `assemble_context.py` used the wrong graphify command (`path` → `explain`) and could
  fall back to another project's `MEMORY.md`; both fixed.
- Restored Python 3.8/3.9 compatibility via `from __future__ import annotations`.
- `count_loc()` no longer treats `"""` inside a C-style block comment as a Python
  block-comment terminator (extension-conditional now).
- `run_hook.sh` version guard uses an explicit exit code instead of `assert`
  (disabled under `python -O`); removed a dead `AI_SUMMARY.md` filter.
- `verify-ai-docs` SKILL: replaced GNU-only `find -printf` with POSIX `find -exec dirname`.
- Removed a hardcoded machine-specific graphify path; corrected docs (graphify URL
  `safishamsi/graphify`, `explain` not `query`, "Garry Tan", tier count, Cursor mechanism).

### Changed
- Extension definitions deduplicated across the three tools (DRY); `source_exts.py`
  renamed to `source_config.py`. CI LOC-gate comment documents the `wc -l` vs
  `count_loc()` distinction.
