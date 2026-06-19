# AI_CONTEXT — anti-debt / debt-scan / tools

## Purpose
The deterministic scanners behind the `debt-scan` skill. Each detects one debt
category and normalizes output to `debt-finding.schema.json`. They prefer real
linters but degrade gracefully (warnings, not crashes) when a tool is absent.

## Key files
- `scan_code.py` — language detection + linter orchestration (ruff/clippy/eslint),
  normalization, and `_augment_python` / `_augment_polyglot` post-processing.
- `heuristic_scan.py` — pure-Python fallback (secrets, long funcs, dead imports,
  duplication, coverage gaps); runs when the linter is missing + always for coverage.
- `scan_security.py` — trufflehog / gitleaks / osv-scanner (secrets + known vulns).
- `scan_deps.py` — cargo-audit / pip-audit / npm-audit / depcruise.
- `aggregate.py` — merge per-tool outputs into one sorted `.debt-scan.json`.
- `run_all.sh` — bash orchestrator with clean exit codes.

## Constraints
- Mint ids via `finding_common.finding_id(...)` (imported from `../../../tools`);
  pass a stable `discriminator` when several findings share file+line+subcategory
  (e.g. rule code, AST hash, import name) — otherwise they collide and dedup drops one.
- `SECRET_PATTERNS` is centralized in `finding_common` — add a pattern ONCE there,
  every scanner inherits it.
- A missing external tool must return a `{"warning": ...}` entry, never raise.

## Forbidden
- Never silently narrow scope: a "complete" scan covers code+security+dependencies
  (see `mvp_runtime` / `scan_periodic`). Skipping a category is the MVP bias the
  agent exists to prevent.
- Never emit a subcategory absent from `../../../taxonomy/debt-categories.yaml`.

## Common failure modes
- Secret detection only runs in the heuristic path (linter absent) — if ruff is
  installed, provider-key detection comes from `scan_security` (trufflehog), not here.
- On Windows + `shell=True`, a missing binary returns rc=1 (not FileNotFound) —
  `run_scanner` does an explicit `shutil.which` check first.

## See also
- `../../../tools/finding_common.py`, `../../../taxonomy/debt-categories.yaml`,
  `../../../tests/test_scan_quality.py`.
