# K1-K4 Measurement Gate — decision record (2026-09-12)

Status: EXECUTED at pilot scale. Scope disclosure: every number below comes from the
controlled corpus (196 Knowledge tests, 11 behavioural E2E A-J, real stores on disk) -
NOT from production usage. Benefit metrics that require a real usage window are marked
NOT MEASURED and are not used to justify any decision.

## Measured (controlled corpus)

| Metric | Measured | Evidence |
|---|---|---|
| Duplicate detection on exact repeats | 100% (2/2 -> MERGE) | E2E-B, tests/test_knowledge_e2e.py |
| Conflict detection on confirmed identities | 100% (2/2 -> NEEDS_HUMAN), never auto-resolved | E2E-C |
| Secret persistence rate | 0 (quarantine refuses, store stays empty) | E2E-F |
| Canonical mutations caused by auto-memory | 0 across every scenario | E2E-B/C/I/J byte-level assertions |
| State transitions caused by advisory passes | 0 (states identical before/after) | consolidation + review tests |
| Recovery classification | exact: RESTORED / STALE_HEAD / DIVERGENCE | E2E-D/E |
| Deterministic retrieval without recall providers | available, explicitly labelled | E2E-G ("no recall providers in core") |
| Staleness signals on changed dependencies | deterministic: POTENTIALLY_STALE, no rewrite | E2E-I |
| Identity refusals (wrong project, out-of-vocabulary segments) | exact, observed live during development | review/import test runs |
| Suite execution cost | 196 tests, ~67 s wall clock | local run, 2026-09-12 |

## NOT MEASURED (requires a real usage window)

- candidate usefulness (precision of captured claims in real sessions)
- review burden over real sessions vs baseline (agent edits Markdown + human Git-diff review)
- retrieval token/byte cost and precision in production contexts
- cross-session recovery value in real work
- promotion frequency (moot: gated)

## Decision

**STOP** — K5 canonical auto-promotion remains disabled.

Rationale: the evidence supports production readiness of K1-K4 (deterministic, fail-closed,
zero canonical mutation, exact recovery classification) but contains NO benefit data for
automation. Authorizing NARROW or FULL without measured usefulness would trade a proven
safety boundary for an unmeasured convenience. The K5 gate in states.py stays closed
(KNOWLEDGE_GATE_CLOSED).

## Consequences

- Auto-Memory core (capture, classifier, working memory, imports, maintenance, staleness,
  consolidation, review) is production-ready WITHOUT canonical auto-promotion.
- "canonical auto-promotion" is intentionally not shipped; it is not debt, it is a measured
  decision.

## Re-evaluation path (when NARROW/FULL may be revisited)

1. Collect a real usage window (captured candidates across actual sessions);
2. re-measure duplicate/conflict/false-positive rates and review burden against baseline;
3. if measured review burden drops below the Git-diff baseline, propose NARROW (initial
   targets: AI_CONTEXT controlled sections, KFP append/deprecate/supersede only);
4. FULL remains out of scope until NARROW is qualified.