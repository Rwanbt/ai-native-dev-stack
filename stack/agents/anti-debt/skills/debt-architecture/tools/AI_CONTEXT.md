# AI_CONTEXT — anti-debt / debt-architecture / tools

## Purpose
Architecture-level debt scanner: detects circular imports and high coupling
across a Python repo. Backs the `debt-architecture` skill. Output conforms to
`debt-finding.schema.json` (category `architecture`).

## Key files
- `scan_architecture.py` — `detect_circular_imports_repo` (DFS over the module
  import graph) and `detect_high_coupling_python` (fan-out count).

## Constraints
- Cycle detection keeps the **full dotted module name** (not just the top-level
  package) so nested-package cycles (`pkg.a <-> pkg.b`) are found, not only
  root-level ones. Imports that don't resolve to a repo module are ignored.
- Findings are heuristic → confidence `0.9` (never claim `1.0`).
- Mint ids via `finding_common.finding_id` (imported from `../../../tools`).

## Forbidden
- Never raise `confidence` to 1.0 for these import-graph heuristics — they miss
  dynamic imports and `from pkg import submodule` forms.

## Common failure modes
- `from pkg import sub` resolves `node.module` to `pkg`, which may not match the
  `pkg.__init__` module key → some cycles via package `__init__` are missed (known).

## See also
- `../../debt-scan/tools/scan_deps.py` (also reports `dependencies/circular` for JS),
  `../../../taxonomy/debt-categories.yaml` (architecture category).
