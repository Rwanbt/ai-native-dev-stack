# Changelog

All notable changes to this project are documented here.

## [Unreleased] — V1.2 (2026-06-17)

### Added
- **Layer 0 — Knowledge Graph** : SQLite-backed KG with 6 node types (Component, Debt, Decision, Fix, Convention, ADR) and 7 edge types. 5 files in `kg/` (schema, store, query, sync, migrate). 22/22 tests.
- **Layer 1 — Static analysis** : `tools/static_analysis.py` for cyclomatic complexity, nesting depth, function size, AST-based duplication, fan-in/fan-out. `tools/polyglot_scan.py` for Rust + JS/TS fallback (CC, god-functions, import cycles). 8/8 tests.
- **Layer 2 — Critic Engine V2** : `tools/critic_v2.py` with confidence tiers (reject / review / accept), override tracking, kill switch (>30% override rate), score formula `(impact × urgency × confidence) / (effort × risk)`. 15/15 tests.
- **Layer 3 — V1.2 skills** : `debt-architecture` (cycles + coupling), `debt-prevention` (rules + regression test generator), `debt-manage` (CLI registry). 14/14 tests.
- **Layer 4 — Orchestration** : `tools/scan_periodic.py` for multi-project scan with scheduling, KG persistence, Telegram/log alerts. 6/6 tests.
- **Layer 6 — Self-update** : `tools/calibration.py` for empirical threshold calibration from override feedback. 8/8 tests.
- **Layer 7 — Dashboard** : `tools/dashboard.py` generating a self-contained HTML dashboard (SVG, no JS framework). 3/3 tests.
- **7 ADRs (0017-0024)** : V-max architecture, threat model, migration, concurrence, critic, versioning, storage, pipeline Layer 4-7.
- **`docs/v-max-design.md`** : synthesis document (32 problems → 7 ADRs → 12-month roadmap).
- **`docs/scoring-calibration.md`** : empirical calibration protocol for the priority score.
- **`examples/projects.example.json`** : example config for `scan_periodic.py`.
- **`examples/sample-real-project-scan.json`** : canonical sample output of a real scan (207 findings on ai-native-dev-stack).

### Changed
- `tools/scan_code.py` (V1.1 bug fixes) :
  - B1: explicit binary check via `shutil.which()` to avoid silent empty results when ruff is missing.
  - B2: heuristic language detection (fallback to file count when no marker file present).
  - B3: `cargo clippy --no-deps --message-format=json` to avoid requiring a full debug build.
  - Added Python AST fallback (secrets via regex, long functions, dead imports, missing docstrings).
  - Added `detect_coverage_gaps` for missing/thin test detection.
  - Added `polyglot_scan` invocation for Rust/JS when toolchain missing.
  - Added Python duplication detection (AST-hash with docstring + identifier normalization).
  - `strict_mode` for missing_docs/dead_code (only emit when project has ruff/mypy/flake8 config).
- `tools/scan_deps.py` : heuristic Python deps fallback when `pip-audit` not installed (mini-base of known-outdated packages).
- `tests/test_scan_quality.py` : filter out warnings (entries without category/subcategory) so they don't count as FP.

### Fixed
- FK constraint failure on `resolves` edges during V1→V2 migration (synthetic Fix nodes with deterministic IDs).
- Idempotency broken by UUID regeneration (now uses V1 `scan_id` as deterministic suffix).
- 6 parasitic `skill1`-`skill6` directories and 5 parasitic `fixture1`-`fixture5` directories (cleaned up).
- `fixture4-py-secure/requirements.txt` was entirely commented out → uncommented.
- `fixture2-rust-complex/` was missing `Cargo.toml` → created minimal one.
- `DUP_MIN_AST_SIZE` was 100 (too high) → reduced to 2.
- Missing `hashlib` import in `scan_code.py`.
- Duplication detection now ignores docstrings + identifier names (was finding 0 matches because docstrings differed).

### Metrics
- `test_scan_quality.py` progression on the 5-fixture corpus:
  - precision: 6.25% → 18.33% → 30.83% → 55.83% → 58.33% → 64.58% → **87.50%**
  - recall: 8.33% → 41.67% → 66.67% → 91.67% → **100.00%**
  - Final score: fixture1 0.75/1.00, fixture2 1.00/1.00, fixture3 0.50/1.00, fixture4 0.50/1.00, fixture5 0.00/1.00 (baseline_clean).

### Total tests
- **76/76 PASS** (22 Layer 0 + 14 Layer 3 V1.2 + 23 Layer 1+2 + 17 Layer 4+6+7).

## [1.0.0] — 2026-06-15 (V1 shippable)

### Added
- 7-commit V1 foundation : agent.md, taxonomy (4 categories × 20 subcategories), 3 JSON schemas, 6 skills (debt-scan, debt-plan, debt-fix, debt-verify, critic, mvp-debt-report), 4 deterministic scanner tools, 5-fixture corpus, 8/8 critic + anti-MVP tests, 3 CLI adapters, CI workflow.
- Hooks Codex universalisés : `D:\App\ai-native-dev-stack\hooks\pretool-graphify-inject` and `permission-readonly-env`.
