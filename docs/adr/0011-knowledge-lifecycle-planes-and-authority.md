# ADR-0011 — Knowledge Lifecycle planes, package and authority boundary

- Status: proposed (Phase K0 — awaits external review, no runtime yet)
- Date: 2026-09-07
- Constrains: `ainative/knowledge/` (new), `docs/KNOWLEDGE-*.md` (new), future
  `ainative knowledge` CLI surface.
- Does not modify: ADR-0001 through ADR-0010. The Verified Work Plane's
  authority architecture is closed and is not reopened here.

## Context

The stack stores and retrieves knowledge (`AGENTS.md`, per-module
`AI_CONTEXT.md`, ADRs, `KNOWN_FAILURE_PATTERNS.md`, Obsidian project Vault,
Graphify output, session notes) but has no deterministic framework for
deciding what deserves to become durable knowledge, what evidence supports
it, whether it duplicates or contradicts existing truth, or when it goes
stale. The implementation plan ("Knowledge Lifecycle & Memory Architecture")
proposes a full lifecycle (CAPTURE to ARCHIVE) with Markdown/Git as
canonical truth.

The risk is a second source of truth: a database, an embedding index or a
session cache that silently becomes authoritative alongside Markdown.

## Decision

### 1. Three data planes, exactly one owner per fact

- **Canonical Knowledge Plane**: human-readable, Git-versioned Markdown
  (`AGENTS.md`, `AI_CONTEXT.md`, `docs/adr/*`, `KNOWN_FAILURE_PATTERNS.md`,
  Vault notes). Durable, diffable, portable. The only plane agents may cite
  as project truth.
- **Transient State Plane**: short-lived operational state (active task,
  hypotheses, pending tests, candidate learnings, compaction checkpoints)
  under `.ai-native/knowledge/transient/`. Bounded, disposable, excluded
  from durable semantic retrieval by default.
- **Derived State Plane**: rebuildable indexes and generated products
  (semantic indexes, Graphify output, ranking caches, context bundles).
  Zero authority. Deletable at any time; `reset-derived + rebuild` must
  preserve every canonical byte.

### 2. Package location: `ainative/knowledge/`

The lifecycle engine lives in `ainative/knowledge/`, beside
`ainative/lifecycle/`, never inside `ainative_workplane/`. Rationale:

- Knowledge reasoning is lifecycle-side (profiles, installation, context),
  not verdict-side. ADR-0009's dependency rule (lifecycle may invoke the
  Work Plane, never the reverse) is preserved trivially: the knowledge
  package MUST NOT be imported by `ainative_workplane/`.
- To keep `ainative init --profile standard` free of authority modules
  (ADR-0009 section 1, `ainative/cli.py` lazy dispatch), the knowledge
  package MUST NOT import `ainative_workplane/` either. Work-plane evidence
  reaches candidates only as caller-supplied serialized records (digests,
  identifiers), never as a live import. Shared vocabulary (provenance
  facts, freshness outcomes) is reused by name with a `knowledge.` scope
  prefix; primitives are not redefined.

### 3. Authority boundary (INV-05 restated as law)

Knowledge may supply read-only context, traceability hints and candidate
provenance. It MUST NOT manufacture `CONVERGED`, `PASS`, `APPROVED` or
`TRUSTED`. It MUST NOT write a trust anchor, approval, work contract,
verification run or convergence record (ADR-0009 section 2 extended to
knowledge promotion). Promotion writes Markdown patches only, against a
known base digest, with human approval per target policy.

### 4. Candidate store: file-based JSONL first, SQLite deferred

Candidates, provenance and audit events live in append-only JSONL under
`.ai-native/knowledge/` (`candidates.jsonl`, `audit.jsonl`), written
atomically via the existing `statelib.write_atomic` pattern and hashed
with `digestlib`. Rationale: readable, diffable, Git-independent,
audit-friendly, zero new dependency (stdlib only, per ADR-0009). SQLite
is allowed later ONLY for operational state metadata and ONLY with an
explicit ADR stating it is not canonical knowledge. No benchmark is
claimed here; the choice is reversibility-first, not performance-first.

### 5. Promotion safety

Every canonical mutation is a patch against a recorded `base_digest`
(`STALE_BASE` aborts, `PROMOTION_CONFLICT` on concurrent change).
`ADD / MERGE / REFINE / SUPERSEDE / REJECT / DEFER` only; `CONFLICT`
remains a candidate state, never a silent auto-resolution. `AGENTS.md`
and ADR targets require human approval, always. `AI_CONTEXT.md`
auto-promotion is forbidden until a later ADR with evaluation evidence.

## Rejected alternatives

**`ainative_knowledge/` top-level package.** Stronger isolation, but splits
the lifecycle layer into two roots for one responsibility (installation,
profiles, context, knowledge). The in-package boundary plus the no-import
rule gives the same guarantee with one ownership home.

**SQLite first.** Better concurrency and querying, but introduces a binary
state file that invites second-source-of-truth drift and needs tooling to
audit. Deferred until JSONL proves insufficient, with a migration ADR.

**Knowledge inside `ainative_workplane/`.** Would let narrative memory
share a package with verdict authority — the exact boundary INV-05
forbids. Rejected outright.

**Semantic score as promotion signal.** Similarity ranks retrieval
candidates; it never decides equivalence, promotion or conflict
resolution. A deterministic or human-reviewable explanation is required.

## Consequences

- Phase K0 delivers docs plus contracts plus this ADR; no runtime code
  lands before external review (`K0 GO`).
- `pyproject.toml` gains `ainative.knowledge` in `packages` when runtime
  lands (additive, no dependency change).
- `ainative doctor` later reports knowledge health read-only; `ainative
  knowledge reset-derived` MUST preserve canonical Markdown, Vault notes,
  Git history, ADRs, KFP, `AI_CONTEXT`, `AGENTS` and audit provenance.
- Threat model extension lives in `docs/KNOWLEDGE-SECURITY.md` and reuses
  `docs/THREAT_MODEL.md` vocabulary; new P0 blockers (stale-base
  overwrite, derived reset deleting canonical, secret persistence,
  prompt-injection escalation, cross-project leakage, unbounded growth)
  gate `GO PRODUCTION`.