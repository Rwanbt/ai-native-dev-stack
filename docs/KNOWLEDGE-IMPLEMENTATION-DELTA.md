# Implementation Delta — branch vs V3.3.1 erratum + review claims

Scope discipline (V3.3.1 S0): the erratum patches approval-evidence
authenticity ONLY; architecture-wide redesign is FORBIDDEN and it
supersedes V3.3 only where inconsistent. Rows marked REVIEW-CLAIM come
from the external review text, not from the erratum file on disk, and
stay open until their frozen source is produced. Pinned branch: `a3f1a83`.

## Decided by V3.3.1 (implementable now)

| Erratum clause | Existing branch | Status | Action |
|---|---|---|---|
| S1 three trust fields (never collapsed) | single `--approve` string, no mode/capability/evidence split | CONFLICTING | `trust.py` receipt model |
| S2 QUAL-T = exposure only, ENFORCEABLE removed | no QUAL-T concept | ABSENT | executed S27 probe: NOT_SEPARATED here |
| S3/S7 ceremony alone is UNVERIFIED | docs implied human approval suffices | CONFLICTING | relabel + enforce UNVERIFIED |
| S4/S11 production rule = evidence_status only | policy.py gates on human string | CONFLICTING for K5 | derive `production_trust_qualified`, quarantine until wired |
| S5/S6/S18/S19 consume existing authority, no duplicate | zero workplane imports (good) but zero consumption either | PARTIAL | inject verifier callback, never copy logic |
| S9/S14/S15 authority_ref mandatory + validated, APPROVAL_AUTHORITY_INVALID | no authority_ref | ABSENT | validation rule + INVALID, no ceremony fallback |
| S13/S20 lifecycle/health/qualification returned separately | PROMOTED conflates; health file-level; no qualification field | PARTIAL | triple return on reconcile/inspect |
| S16 forged VERIFIED claim -> INVALID | no such check | ABSENT | E2E-AU test |
| S22 production-safe policy (HEALTHY + VERIFIED/ATTESTED) | no policy coupling | ABSENT | enforce in promote path |
| S24 ceremony-only E2E-AV | covered mechanically, qualification unlabeled | PARTIAL | label UNVERIFIED |
| S25 verified approval E2E-AW (fresh clone, no local state) | no authority-backed path | ABSENT | implement via injected verifier + fixture authority |
| S26 digest binding (decision/assertion/target/op/scope/base/result) | base/result digests only; no approval_digest | PARTIAL | bind exact digest; replay (AX) rejected |
| S27 trust-root accessibility probe | never probed | DONE (UNSAFE here) | K0-A matrix |
| S28 per-section health (HEALTHY/REVERTED/SUPERSEDED/MISSING/AMBIGUOUS) | file-level HEALTHY/recovered only | CONFLICTING | section spans + resolver |
| S29 E2E-AY supersession semantics | SUPERSEDED is a candidate state, not span health | PARTIAL | span-level AY test |

## Review claims outside this erratum (source not on disk — open)

4 planes + Local/Project Audit split; identity_key grammar + assertion
hash; structured-claim source binding beyond evidence locators; single
ContextPlanner unification; STOP/NARROW/FULL measurement gate; B1/B2/B3
contract texts (named but undefined in the erratum); cross-project
isolation E2E; fresh-clone promotion AQ. These are NOT decided by
V3.3.1-S0 scope. They stay open; nothing here forecloses them, and no
code below claims them.

## Quarantine (unchanged)

Promotion path = STANDARD/UNVERIFIED until authority wiring lands.
Last-writer-wins append stands (P1). V1 phase numbering stays frozen
in history; new work uses erratum + review phase names explicitly.