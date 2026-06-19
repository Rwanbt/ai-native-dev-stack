# AI_CONTEXT — anti-debt / debt-prevention / tools

## Purpose
Turns recurring findings into prevention: generates linter/config rules and a
regression guard so a fixed pattern cannot silently come back. Backs the
`debt-prevention` skill.

## Key files
- `prevent_finding.py` — `aggregate_patterns` (group by category/subcategory,
  threshold ≥ 3), `generate_rule` (emit a tool config from `RULE_TEMPLATES`),
  `generate_regression_test` (emit a test asserting the rule stays in place).

## Constraints
- Config templates must be valid for their target tool (e.g. `ruff.toml` uses the
  top-level `[lint]` schema, not `[tool.ruff]`).
- Generated configs carry the `anti-debt-agent` marker so re-runs are idempotent
  (append once) and the regression test can assert the guard's presence.

## Forbidden
- Never emit a tautological regression test (`assertTrue(True)`) — the generated
  test must actually verify the prevention rule exists and is non-empty.

## Common failure modes
- A `(category, subcategory)` with no entry in `RULE_TEMPLATES` yields no rule —
  `generate_regression_test` returns `None` rather than a fake passing test.

## See also
- `../../../docs/v-max-design.md` (Layer 6 — Prevention Generation).
