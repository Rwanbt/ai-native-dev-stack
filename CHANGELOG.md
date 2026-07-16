# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
- `install.sh` step 2 now also copies `commit-convention` into
  `.claude/skills/` of the target project, alongside the existing
  `verify-ai-docs` and `verify-standards`.

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
