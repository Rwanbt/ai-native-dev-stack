# Knowledge Security — threat model extension for the Knowledge Lifecycle

Status: Phase K0 (proposed). Parent: ADR-0011. Extends `docs/THREAT_MODEL.md`
without reopening Work Plane authority. Every P0 here gates `GO PRODUCTION`.

## 1. Stored prompt injection

Retrieved text is data, never authority. Every context bundle labels each
excerpt `SYSTEM RULE | CANONICAL PROJECT KNOWLEDGE | RETRIEVED NOTE |
UNVERIFIED CANDIDATE | EXTERNAL CONTENT`. Instructions inside notes,
candidates, Vault content or repository text MUST NOT override system or
`AGENTS.md` rules. E2E-10 (`Ignore AGENTS.md...` inside a note treated as
content only) is a release gate. Consolidation prompts quote untrusted
content as data and never execute embedded instructions.

## 2. Secret handling

Candidate capture runs secret detection BEFORE persistence (API keys,
tokens, credentials, private keys, cookies, authorization headers). On
match: `REJECTED_SECRET`, nothing persisted. Detection is pattern-based
defense in depth (same residual risk as `THREAT_MODEL.md`: patterns can
miss), so persisted evidence keeps digests plus bounded previews, never
full logs. E2E-11 gates release.

## 3. Path security

All file operations reuse the lifecycle confinement pattern
(`ainative/lifecycle/paths.py`): resolve, normalize, verify root
confinement, reject traversal, reject unsafe symlink/junction escape with
`PATH_ESCAPE`. Candidate-supplied locators, import payloads and journal
ids are validated before they become filenames. Case-collision and
device/FIFO rules from `FRESHNESS_POLICY.md` apply to snapshot reads.

## 4. Cross-project and cross-agent leakage

Candidates carry project slug plus scope/visibility; retrieval filters on
both. A query for project A MUST NOT return project B notes, private
scopes, or another agent''s non-promoted observations. Scope widening
happens ONLY at promotion, explicitly. Cross-harness imports are
quarantined as candidates until reviewed.

## 5. Canonical mutation safety

Stale-base write: promotion records `base_digest` at evaluation and
re-validates before replace; mismatch is `STALE_BASE`, abort, no write.
Concurrent agents: optimistic concurrency (`base_digest`,
`target_digest`, `candidate_id`); second writer gets `PROMOTION_CONFLICT`
(E2E-09). Crash mid-write: temp write, validate, atomic replace, then
audit event; recovery reconciles a missing event without fabricating
state. Migration MUST NOT destructively rewrite existing Vault,
`AGENTS.md`, `AI_CONTEXT.md` or session notes (additive only).

## 6. Second-source-of-truth prevention

`candidates.jsonl` plus `audit.jsonl` hold candidate/state metadata ONLY.
Any read path treating them as project truth is a P0. Derived reset MUST
NOT delete canonical knowledge; E2E-12 (delete all derived state,
rebuild, retrieval returns equivalent knowledge) gates release.
`ainative_workplane/` MUST NOT import `ainative/knowledge/` and knowledge
MUST NOT import the Work Plane (ADR-0011): neither direction can smuggle
narrative memory into verdict authority or vice versa.

## 7. Availability and bounded growth

Semantic/Graph/Vault providers are optional; degraded mode (deterministic
context only, explicit status) is the fallback, never a hard failure
(E2E-06/07/08). Transient plus derived state enforce `max age / entries /
bytes / checkpoints`; unbounded growth is a P0. Candidate spam (bulk
low-evidence capture) is rate-bounded and never auto-promoted.

## 8. P0 security blockers (release gates)

Canonical overwrite from stale base. Derived reset deleting canonical
knowledge. Candidate promotion without provenance. Prompt-injected note
overriding system/project authority. Silently persisted secret.
Cross-project retrieval leakage. Silent concurrent-promotion overwrite.
Mandatory semantic provider. Mandatory Vault for core operation. Work
Plane accepting narrative knowledge as verification evidence. Hidden
SQLite/index canonical truth. Unbounded transient state. Unauditable
promotion. Destructive Vault migration. Any unresolved P0 is NO-GO.