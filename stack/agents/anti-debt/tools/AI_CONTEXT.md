# AI_CONTEXT — anti-debt / tools

## Purpose
Core engine of the technical-debt agent: deterministic analysis + the Critic.
These are CLI tools (each runnable as `python3 <tool>.py`) orchestrated by the
skills. They produce/triage findings that conform to `../schemas/`.

## Key files
- `finding_common.py` — **shared primitives**: `finding_id()` (deterministic
  fingerprint = id of a finding) and `SECRET_PATTERNS` (used by every scanner).
- `critic_v2.py` — Critic Engine: confidence tiers (`reject<0.6 / review<0.7 /
  accept`), `build_triage()` (deterministic), scoring, override tracking.
- `static_analysis.py` — Python AST metrics (CC, length, nesting, duplication, fan-out).
- `polyglot_scan.py` — toolchain-free Rust/JS scanner (regex/brace heuristics).
- `mvp_runtime.py` — end-to-end scan→triage→dry-run orchestrator.
- `calibration.py` — recalibrate Critic thresholds from override history.
- `scan_periodic.py` — multi-project scheduler + KG persistence + alerts.
- `dashboard.py` — self-contained HTML dashboard from the KG.
- `validate_plan.py` / `validate_adapters.py` — schema/adapter gates.

## Constraints
- **Finding identity is deterministic** — always mint ids via
  `finding_common.finding_id(category, subcategory, file, line, discriminator)`,
  NEVER `uuid4()`. Random ids break dedup, the KG and history.
- The Critic reject floor `0.6` is the non-negotiable policy — keep
  `critic_v2.TIER_REJECT` and `calibration.DEFAULT_REJECT` in sync.
- The scoring formula lives in ONE place (`critic_v2.compute_score`) and is
  documented in `../docs/scoring-calibration.md` — keep them aligned.

## Forbidden
- Never emit an `evidence.type` / `source` / `category` outside the
  `debt-finding.schema.json` enums (the `test_schema_conformance` guard fails CI).
- Never put a remediation `actions`/`accepted_debt` plan here — that is the LLM
  `debt-plan` skill's job (`debt-plan.schema.json`). This layer is deterministic.

## Common failure modes
- Adding a scanner that mints `uuid4()` ids → KG accumulates duplicate Debt nodes.
- Editing the scoring formula in the doc but not the code (or vice-versa).
- Using `python` instead of `python3` in a subprocess on Linux CI.

## See also
- `../kg/` (Knowledge Graph), `../skills/debt-scan/tools/` (scanners),
  `../docs/scoring-calibration.md`, `../schemas/`.
