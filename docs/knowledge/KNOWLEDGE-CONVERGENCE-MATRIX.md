# Knowledge Convergence — Legacy Capability Parity Matrix (initial audit)

Source of truth: `dev` @ a4dfe35 (K1-K4 owners). Legacy reference: `knowledge-lifecycle` @ 9eb5422 (140 behind, 14 ahead).
Progress: 8/18 treated (rows 2, 7, 18 ported; row 13 superseded by the planner).
This is the STATIC audit (file/docstring/inventory level). Behavioral verification and the final
`PORTED / SUPERSEDED / INTENTIONALLY_DROPPED` audit (no UNKNOWN) come before any branch deletion.

## Owner freeze (no duplicates allowed)

| Concept | Owner on dev |
|---|---|
| identity / schema / assertion hash / state machine | knowledge/identity.py, assertions.py, states.py |
| storage / locked store | knowledge/store.py |
| secret quarantine | knowledge/quarantine.py |
| context selection / retrieval | knowledge/planner.py (single ContextPlanner) |
| graph | knowledge/graph.py |
| semantic | knowledge/semantic.py |
| working continuity / checkpoints | knowledge/continuity.py |
| support / conflict / dedup / normative resolution | knowledge/resolution.py |
| bounds / envelope / scope / paths / errors | knowledge/{bounds,envelope,scope,paths,errors}.py |
| project lifecycle / transactions / locks | ainative.lifecycle |
| verified authority / trust root | ainative_workplane (existing) |
| vault isolation | Multi-Vault owners (ainative.multivault) |

## Capability matrix (legacy -> dev)

| # | Capability | Legacy artifact | Dev owner | Static status | Port strategy |
|---|---|---|---|---|---|
| 1 | Candidate capture (proposal schema, state machine, capture-time validation) | candidate.py (263 l) | assertions.py + states.py + store.py + cli.py (K1) | COVERED (verify behaviorally) | extend capture provenance fields only |
| 2 | Advisory classification (kind + reasons) | classifier.py (43 l) | classifier.py (ported 9a973bf) | PORTED | port as pure keyword heuristic; advisory-only contract; versioned categories; UNKNOWN never guessed |
| 3 | Consolidation cycle (collect/cluster/propose, advisory) | consolidation.py (156 l) | consolidation.py (ported wave 7, composes resolution) | PORTED | extend resolution with advisory `knowledge consolidate`; zero canonical writes |
| 4 | Dedup relations (exact/containment/lexical, SEMANTIC_AMBIGUITY human-gated) | dedupe.py (177 l) | resolution.py (K4) | LIKELY COVERED | behavioral verify; port gaps into resolution only |
| 5 | Evidence accumulation (idempotent reinforce, sufficiency rule) | evidence.py (73 l) | resolution.py / assertions.py | PARTIAL | verify idempotence + sufficiency; verification stays a referenced proof, never owned here |
| 6 | Health (read-only status/doctor) | health.py (68 l) | status/report surface | PARTIAL | extend `ainative doctor` with Knowledge section (program section 24) |
| 7 | Cross-harness import (preview/apply, staged as candidates) | imports.py (149 l) | imports.py (ported 43dec88) | PORTED | port preview/apply staging; never canonical direct import; preserve harness provenance |
| 8 | Derived-state maintenance (maintain/export/reset-derived, owner-composed) | maintenance.py (50 l) | maintenance.py (ported wave 5) | PORTED | port small; registry-based, reconstructibility proof |
| 9 | Approval policy (per-class table, human-gated) | policy.py (79 l) | none (K5) | MISSING | port with K5 gate decision; conservative default |
| 10 | Promotion engine (audited minimal patch, base digest, atomic) | promotion.py (487 l) | none (K5) | MISSING | implement on ainative.lifecycle transactions (B3 spec), NOT a cherry-pick; no second transaction engine |
| 11 | Candidate provenance (who/where/git state, degraded OK) | provenance.py (77 l) | identity/assertions (partial) | PARTIAL | extend capture provenance; best-effort git; never import workplane on Standard |
| 12 | Provider contracts (optional, probe/degraded, injected) | providers.py (189 l) | graph.py + semantic.py (K2) | PARTIAL | verify optional/degraded contract; providers feed planner Sources only |
| 13 | Retrieval (deterministic-first, budgets, UNVERIFIED notes, recall gating) | retrieval.py (346 l) | planner.py (single ContextPlanner) | SUPERSEDED | port only verified behavior gaps INTO planner; never a second retrieval engine |
| 14 | Review exposure (queue, conflicts, priorities; transitions owned by states.py) | review.py (116 l) | review.py (ported wave 8) + states.py | PORTED | verify hop-by-hop audit trail; NEEDS_EVIDENCE/SUPPORTED/DUPLICATE/CONFLICTING |
| 15 | Staleness (dependency signals, decay ranking-only, no auto rewrite) | staleness.py (178 l) | staleness.py (ported wave 6) | PORTED | port impact scan; GIT_HISTORY evidence candidates; decai only priority |
| 16 | Promotion targets (narrow subset, explicit --target) | targets.py (77 l) | none (K5) | MISSING | port narrow subset (AI_CONTEXT sections, KFP); Vault/AGENTS/ADR auto-promotion forbidden initially |
| 17 | Trust receipts (3 orthogonal fields, V3.3.1 erratum) | trust.py (141 l) | none; authority exists in ainative_workplane | MISSING | port model onto existing authority via minimal owner API; STANDARD ceremony = UNVERIFIED, honestly |
| 18 | Working memory (bounded fields, TTL, crash-safe) | working.py (330 l) | continuity.py (extended 34d4b64) | PORTED | extend continuity; CLI `ainative context save/status/checkpoint/restore/clear`; no raw CoT |

## Legacy test inventory (15) — migration status pending behavioral pass

test_knowledge_{candidate,consolidation,promotion,providers,retrieval,review,staleness,trust,working,cli,context,e2e,import,perf,promote}.py
Each will be classified: already covered / still relevant / obsolete due to frozen spec / must be ported / must be rewritten against the new owner.

## Notes

- Legacy also carried `ainative_workplane/{evidence,provenance,trust}.py`; dev's `ainative_workplane` package is authoritative — those legacy files are NOT ported.
- K5 measurement gate must run for real (section 15 of the program) before any promotion work; STOP/NARROW/FULL decided by data, not ambition.
- No deletion of `knowledge-lifecycle` before the final parity audit reaches PORTED/SUPERSEDED/INTENTIONALLY_DROPPED with zero UNKNOWN.