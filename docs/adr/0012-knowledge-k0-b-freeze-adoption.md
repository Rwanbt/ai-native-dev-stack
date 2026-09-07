# ADR-0012 — Knowledge Lifecycle K0-B freeze adoption

- Status: accepted
- Date: 2026-09-07
- Constrains: `docs/K0-B1-*.md`, `docs/K0-B2-*.md`, `docs/K0-B3-*.md`,
  `docs/K0-B-FREEZE-INDEX.md`, all future Knowledge Lifecycle work.
- Does not modify: ADR-0001 through ADR-0008. The Verified Work Plane's
  authority architecture is closed and is consumed, never reopened.

## Context

ADR-0011 froze an interim architecture (three data planes, JSONL-first
store, human `--approve` promotion) sufficient to build a prototype.
External review against the frozen specifications (V3.3.1 trust-closure
erratum, K0-B1/B2/B3 freeze contracts) plus executed K0-A probes
(`docs/K0-A-CAPABILITIES.md`, PR0) established three facts:

1. The `TRUST_BOUNDARY_NOT_SEPARATED` profile and the UNSAFE Work Plane
   trust root make any production-trust claim for the current promotion
   path incorrect. Ceremony-only promotion is STANDARD / UNVERIFIED.
2. The durable-control split (Local Control Payload vs Project Audit
   Control), root-specific `identity_key`, structured-claim binding and
   the unified ContextPlanner are frozen contracts the prototype does
   not satisfy yet.
3. K5 (canonical promotion) is conditional on K1–K4 measurements
   (`STOP / NARROW / FULL`) and stays out of the initial merge sequence.

## Decision

Adopt as frozen normative references:

```text
docs/K0-B1-CAPTURE-CONTROL-FREEZE.md
docs/K0-B2-CONTEXT-AUTHORITY-FREEZE.md
docs/K0-B3-MUTATION-TRUST-FREEZE.md
docs/K0-B-FREEZE-INDEX.md
```

plus the V3.3.1 trust-closure erratum for approval authenticity.

Adjust ADR-0011 without rewriting history:

- The three-plane model is superseded by the four-class model
  (Canonical / Transient / Derived / Durable Control, the latter split
  into Local Payload and Project Audit) for all future work.
- The existing promotion runtime (`ainative/knowledge/promotion.py`,
  `policy.py`, `knowledge promote`) is classified STANDARD /
  UNVERIFIED and quarantined from production claims until the K5 gate.
- V1 phase numbering (K1 = candidate core, K2 = working state, …) is
  retired for future issues and ADRs; the review sequence
  (K1 capture+measurement, K2 ContextPlanner, K3 continuity, K4
  support/conflict/dedup, conditional K5) is authoritative going forward.
- Jaccard/sufficiency/budget constants remain named experimental
  defaults until benchmarked per B1 §15 / B2 §25.

## Rejected alternatives

**Rewrite ADR-0011 in place.** History must show what the prototype was
built against; supersession notes preserve the trail while the freeze
contracts govern new work.

**Fold the freeze texts into this ADR.** The contracts are long-lived
normative references with their own GO status; an ADR points at them,
it does not duplicate them.

**Authorize K5 preparation merges alongside.** Preparation without the
measurement gate is how the prototype overran its authority once
already; the gate stays closed until K1–K4 measure.

## Consequences

- PR0 (K0-A evidence) and PR1 (these contracts + this ADR) are
  docs-only and independently reviewable.
- PR2+ runtime work must cite the applicable B-clause per change and
  the E2E gate it satisfies.
- Any future relaxation (target-class auto-promotion, threshold
  hardening, shared-scope defaults) needs its own ADR with evaluation
  evidence — never a silent flag flip.
- The `ainative/knowledge/` package path is reclaimed by the
  B1-conformant implementation (PR2+). The V1 prototype branch must be
  renamed before any rebase onto main; a silent path collision on
  rebase is a merge hazard.
