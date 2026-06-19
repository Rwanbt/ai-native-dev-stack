# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project aims to adhere to [Semantic Versioning](https://semver.org/) once tagged
releases begin.

## [Unreleased]

### Added
- `VERSION` (semver) + `stack-version` header in `AGENTS.md` — version source of truth.
- `scripts/stack-update-check.sh` — read-only upstream-update detection (fetch + compare).
- `scripts/stack-upgrade.sh` — non-destructive fast-forward-only upgrade; aborts on a
  dirty tree, touches only the shared repo, reports changed `*.example` templates.
- `skills/stack-upgrade/SKILL.md` — `/stack-upgrade` command (gstack-style).
- `UPDATING.md` — the non-destructive update model ("reference, don't copy") + the
  managed-block convention for the rare inlined case.
- `tools/ai_docs/source_config.py` — replaces `source_exts.py`; now also exports
  `EXCLUDE_DIRS`, the unified directory exclusion set shared by all tools.
- `tools/ai_docs/module_discovery.py` — shared `find_module()` function, eliminating
  the divergent duplicate (str vs Path signature) between `update_on_edit.py` and
  `assemble_context.py`.
- `parse_fsharp()` — best-effort F# parser (modules, types, public `let` bindings).
  F# files (`.fs`, `.fsi`) are no longer silently routed to `parse_csharp()`.
- `test_flat_module_constraint_nested_files_not_scanned` — documents the intentional
  flat-module scanning behaviour.
- 12 new tests: `TestSourceConfig`, `TestModuleDiscovery`, F# parser tests,
  `TestFlatModuleConstraint`, `count_loc` regression tests for C-style block comments.
- Documented the flat-module constraint (AI_CONTEXT.md and source files must be direct
  siblings) in `README.md`, `CONTRIBUTING.md`, and the `AI_CONTEXT_template.md`.
- `settings_hook_example.json` now includes setup notes and a manual verify command
  to prevent the ALL-CAPS placeholder from silently breaking the hook.

### Fixed
- `generate_metrics.py` now normalises Windows backslashes before passing paths to git.
- `run_hook.sh` version guard now uses an explicit exit code instead of `assert`
  (which is disabled by `python -O`).
- Removed dead filter `f.name != "AI_SUMMARY.md"` in `generate_ai_summary.py`
  (`.md` is never in `ALL_SOURCE_EXTS`).
- `count_loc()` no longer misidentifies `"""` inside a C-style block comment as a
  Python block-comment terminator. Block-close detection is now conditional on the
  file extension.
- `skills/verify-ai-docs/SKILL.md` Tier 2b and 2d: replaced GNU-only `find -printf`
  with POSIX-compatible `find -exec dirname` (was silently returning 0 on macOS).
- Added Python 3.8 to the CI matrix with `continue-on-error: true` (3.8 is EOL
  but the stack claims compatibility).

### Changed
- `source_exts.py` renamed to `source_config.py` — now also exports `EXCLUDE_DIRS`
  (unified from the previously divergent `SKIP_DIRS` in `generate_all.py` and
  `generate_metrics.py`, and `STOP_DIRS` from module discovery).
- CI LOC gate comment now documents the `wc -l` vs `count_loc()` distinction.

### Previous entries
- `tools/ai_docs/source_exts.py` — single source of truth for source-file
  extensions, imported by the summary generator, the hook, and the metrics tool.
- `tools/ai_docs/generate_metrics.py` — objective, git-derived stack metrics
  written to `docs/METRICS.md` (coverage, freshness, drift, KFP/ADR counts,
  risk zones, append-only trend).
- `tools/ai_docs/tests/` — zero-dependency `unittest` suite for the tooling
  (LOC counter, language parsers, summary generation, ADR-ref extraction,
  module discovery, metrics coverage).
- `.github/workflows/ci.yml` — CI running the test suite on Python 3.9/3.11/3.13
  plus a LOC-budget gate that enforces the stack's own 1500-LOC rule.
- `.gitattributes` — forces LF on `.sh`/`.py`/`.yml` so hooks and CI never break
  on CRLF.
- `CONTRIBUTING.md` and this `CHANGELOG.md`.
- `PYTHON_BIN` config option in `config.sh.example`, now honored by
  `find_python.sh` (previously documented but never read).

### Fixed
- `install.sh` did not copy `generate_metrics.py`, so metrics generation was
  broken on every fresh install.
- `generate_metrics.py` listed `AI_CONTEXT.md`/`AI_SUMMARY.md` (file names) in
  `SKIP_DIRS`, forcing module coverage to a permanent 0%.
- `assemble_context.py` invoked `graphify path <file>` (wrong command, single
  arg) and silently swallowed the error; replaced with `graphify explain <node>`
  guarded on the graph existing.
- `assemble_context.py` could fall back to another project's `MEMORY.md`;
  it now returns nothing rather than risk leaking foreign context.
- Restored Python 3.8/3.9 compatibility (PEP 604 `X | None` annotations) via
  `from __future__ import annotations`.
- Removed a hardcoded machine-specific graphify path.
- Documentation: corrected the graphify URL (`safishamsi/graphify`), the
  graphify CLI example (`explain`, not `query`), "Garry Tan", the verify-ai-docs
  tier count (10), and the Cursor AGENTS.md mechanism.

### Changed
- Extension definitions deduplicated across the three tools (DRY).

## Notes

This project is not yet versioned with git tags. The first tagged release will
move the entries above into a `## [x.y.z] - YYYY-MM-DD` section.
