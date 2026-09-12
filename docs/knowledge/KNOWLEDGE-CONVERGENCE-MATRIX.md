# Knowledge Convergence — Legacy Capability Parity Matrix

STATUS: HISTORICAL INITIAL AUDIT + FINAL PARITY RECORD

Current qualified release candidate: v2.2.1

Initial baseline: `dev` @ a4dfe35 (K1-K4 owners). Legacy reference: `knowledge-lifecycle` @ 9eb5422,
archived as tag `archive/knowledge-lifecycle-final`; the branch was deleted after the convergence.

Final result: 18/18 explicit destinies — 13 PORTED, 2 SUPERSEDED, 3 INTENTIONALLY DROPPED (all linked
to the K5 STOP decision), no UNKNOWN. Behavioural E2E A-J green, K1-K4 gate executed (STOP), isolation
E2E green. The body below is the initial STATIC audit (file/docstring/inventory level) kept as the
historical record of the convergence; the final destinies and their evidence are in the audit section
at the end.

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

| Legacy test | Destiny | Evidence |
|---|---|---|
| candidate | SUPERSEDED by test_knowledge_store/states/cli + E2E-A | ae79c86 |
| consolidation | PORTED as test_knowledge_consolidation | fbe22e5 |
| promotion | INTENTIONALLY DROPPED (K5 STOP) | 1b214f4 |
| providers | SUPERSEDED by planner degraded-mode tests + E2E-G | ae79c86 |
| retrieval | SUPERSEDED by test_knowledge_planner | K2 PR |
| review | PORTED as test_knowledge_review | 010b30a |
| staleness | PORTED as test_knowledge_staleness | 97ffc4b |
| trust | REPLACED by the honest exposure tests + measurement gate | 1b214f4 |
| working | PORTED into test_knowledge_continuity | 34d4b64 |
| cli | SUPERSEDED by test_knowledge_cli | K1 PR |
| context | SUPERSEDED by continuity + E2E-D | ae79c86 |
| e2e | PORTED as test_knowledge_e2e (A-J) | ae79c86 |
| import | PORTED as test_knowledge_import | 43dec88 |
| perf | INTENTIONALLY DROPPED (legacy engine timings not applicable; suite cost tracked in the gate artifact) | 1b214f4 |
| promote | INTENTIONALLY DROPPED (K5 STOP) | 1b214f4 |

## Notes

- Legacy also carried `ainative_workplane/{evidence,provenance,trust}.py`; dev's `ainative_workplane` package is authoritative — those legacy files are NOT ported.
- K5 measurement gate must run for real (section 15 of the program) before any promotion work; STOP/NARROW/FULL decided by data, not ambition.
- No deletion of `knowledge-lifecycle` before the final parity audit reaches PORTED/SUPERSEDED/INTENTIONALLY_DROPPED with zero UNKNOWN.

## FINAL PARITY AUDIT - 18/18 explicit destinies (2026-09-12)

No UNKNOWN. PORTED = capability lives on a current owner with tests; SUPERSEDED = the
capability is provided by a different current architecture; INTENTIONALLY DROPPED = a
normative decision, with its reason recorded.

| # | Capability | Destiny | Owner / evidence | Commit |
|---|---|---|---|---|
| 1 | Candidate capture | PORTED | K1 assertions/states/store/cli; E2E-A restart persistence | ae79c86 |
| 2 | Advisory classification | PORTED | classifier.py + test_knowledge_classifier (display-only) | 9a973bf |
| 3 | Consolidation | PORTED | consolidation.py + test_knowledge_consolidation (advisory) | fbe22e5 |
| 4 | Dedup relations | PORTED | resolution.py exact-hash + tombstone + conflict-before-dedup; E2E-B/C. Containment/lexical auto-equivalence DROPPED by design (semantic similarity never decides equivalence - legacy INV-04 kept) | ae79c86 |
| 5 | Evidence accumulation | PORTED | support records + support_summary (resolution). Evidence-type catalog DROPPED (free-form kinds survive; the catalog enforced nothing) | K4 PR + ae79c86 |
| 6 | Health | PORTED | doctor Knowledge section + storage_status + checkpoint_status | 6d0e501 |
| 7 | Cross-harness import | PORTED | imports.py + test_knowledge_import (preview/apply, owner identity, quarantine) | 43dec88 |
| 8 | Maintenance | PORTED | maintenance.py + test_knowledge_maintenance (owner-composed, dry-run default) | a8a5154 |
| 9 | Approval policy | INTENTIONALLY DROPPED | K5 STOP: a policy table for a gate that refuses by design would be dead policy | 1b214f4 |
| 10 | Promotion engine | INTENTIONALLY DROPPED | K5 STOP with evidence-based re-evaluation path (usage window -> NARROW) | 1b214f4 |
| 11 | Provenance | PORTED | record + import provenance (harness/origin project/repo/session); ambient immunity E2E; git state via staleness git_head deps | f632e14 |
| 12 | Provider contracts | SUPERSEDED | planner core is provider-free by design ("no recall providers in core", E2E-G); providers absent = degraded, doctor reports ABSENT | ae79c86 + 6d0e501 |
| 13 | Retrieval | SUPERSEDED | single ContextPlanner (K2); legacy engine never replicated | K2 PR |
| 14 | Review | PORTED | review.py queue/conflicts + states machine hops | 010b30a |
| 15 | Staleness | PORTED | staleness.py + test_knowledge_staleness; E2E-I | 97ffc4b |
| 16 | Promotion targets | INTENTIONALLY DROPPED | K5 STOP: no targets exist without promotion | 1b214f4 |
| 17 | Trust receipts | PORTED (exposure) + receipts DROPPED with K5 | review exposes TRUSTED_OPERATOR_CEREMONY/UNVERIFIED; three-axis model documented in the gate; no fake VERIFIED anywhere (tested) | 010b30a + 1b214f4 |
| 18 | Working memory | PORTED | continuity.py extended (bounded fields, TTL, divergence); E2E-D/E | 34d4b64 |

Tally: 13 PORTED - 2 SUPERSEDED - 3 INTENTIONALLY DROPPED (rows 9, 10, 16, all K5-linked),
with two design-level drops inside PORTED rows (4: auto-equivalence relations; 5: type catalog),
each with a normative reason above.

Legacy `ainative_workplane/{evidence,provenance,trust}.py` shadow files: NOT ported - the
current `ainative_workplane` package is authoritative.

**knowledge-lifecycle deletable = YES** (archive tag first; the deletion itself belongs to the
release cleanup phase, after the PR/merge/release chain per the program).
