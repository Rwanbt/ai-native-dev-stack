# AI_CONTEXT — anti-debt / kg

## Purpose
Layer 0: the **Knowledge Graph** (SQLite) — the source of truth for debt over
time. Nodes (Component, Debt, Decision, Fix, Convention, ADR) and typed edges
(causes, resolves, affects, supersedes, blocks, documents, conflicts) let the
agent answer causal queries ("which debts affect X?", "what does this fix touch?").

## Key files
- `kg_schema.py` — `Node`/`Edge` dataclasses, SQL schema (WAL, FKs, indices),
  migration registry. Validates types in `__post_init__`.
- `kg_store.py` — `KgStore`: idempotent UPSERT CRUD (UNIQUE on node id and on
  edge source+target+type).
- `kg_query.py` — read-only causal queries; BFS traversals are cycle-guarded.
- `kg_sync.py` — KG → Vault markdown snapshots + ADR import.
- `kg_migrate.py` — V1 JSON (`.debt-scan`/`.debt-history`/`.debt-plan`) → V2 KG.

## Constraints
- **All ids must be deterministic** so re-runs are idempotent. `kg_migrate`
  uses `_stable_hash` (hashlib), NEVER the builtin `hash()` (salted per process).
- Upserts are idempotent by design — re-importing the same input is a no-op.
- One canonical DB location: `kg/data/kg.db` (shared by `scan_periodic` and the
  `registry` skill). Don't introduce a second path.

## Forbidden
- Never create self-loop edges (source == target) — the dataclass raises.
- Never store a DebtTriage (`fix_order`) where a DebtPlan (`actions`) is expected;
  `kg_migrate` guards against it (would silently record actions_count=0).

## Common failure modes
- Using builtin `hash()` for ids → cross-process non-idempotency (duplicate nodes).
- Unbounded BFS on a `causes` cycle → guarded by the on-path check in `kg_query`.

## See also
- `../docs/adr/0023-storage-architecture-v2.md`, `../tools/scan_periodic.py`,
  `../skills/debt-manage/tools/registry.py`.
