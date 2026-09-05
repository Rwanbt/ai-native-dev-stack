# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

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
