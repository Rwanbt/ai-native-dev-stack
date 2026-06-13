# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project aims to adhere to [Semantic Versioning](https://semver.org/) once tagged
releases begin.

## [Unreleased]

### Added
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
