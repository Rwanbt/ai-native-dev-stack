# AI_CONTEXT — anti-debt / debt-manage / tools

## Purpose
The Debt Registry CLI behind the `debt-manage` skill: CRUD over accepted/owned
debts, persisted as `Debt` nodes in the Knowledge Graph (Layer 0). Commands:
`register`, `update-status`, `query`, `assign`.

## Key files
- `registry.py` — argparse CLI; each command opens a `KgStore` and upserts.

## Constraints
- Default DB is the canonical `../../../kg/data/kg.db` (`DEFAULT_KG_DB`) — the
  SAME database the scanners write to, so governance and detection share state.
  Don't point it at a private path.
- `register` requires a justification `reason` of ≥ 50 chars (anti "silent debt").
- Status is one of `open | in_progress | accepted | resolved`.

## Forbidden
- Never write the registry to a second KG location (e.g. `~/.mavis/kg.db`) — it
  would desync from the scanners' findings.

## See also
- `../../../kg/` (KgStore/Node), `../../../kg/AI_CONTEXT.md`.
