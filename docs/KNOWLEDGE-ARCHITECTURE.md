# Knowledge Architecture — data planes, candidate contract, promotion rules

Status: Phase K0 (proposed, awaits external review). Parent decision:
ADR-0011. This document is the data-plane contract; runtime behaviour MUST
match it before `K0 GO`.

## 1. Data planes

Every knowledge-related byte belongs to exactly one plane.

| Plane | Location (examples) | Properties |
|---|---|---|
| Canonical | `AGENTS.md`, `AI_CONTEXT.md`, `AI_SUMMARY.md`, `docs/adr/*`, `KNOWN_FAILURE_PATTERNS.md`, Vault `decisions/ architecture/ research/ incidents/ work/ _memory/` | durable, auditable, diffable, human-editable, portable |
| Transient | `.ai-native/knowledge/transient/` (working state, checkpoints, candidate drafts) | bounded, disposable, crash-safe, excluded from durable semantic retrieval |
| Derived | semantic indexes, Graphify output, ranking caches, context bundles, scorecards | zero authority, resettable, rebuildable from canonical |

Laws: Markdown/Git is canonical (INV-01). Derived state MUST be
rebuildable with zero canonical loss (INV-02). Transient state MUST NOT
appear in durable retrieval unless explicitly filtered (INV-03). No store
— SQLite, embeddings, caches, manifests — is a second source of truth
(INV-06). Every canonical mutation carries candidate, evidence, decision,
target, diff, provenance, timestamp (INV-07).

## 2. Candidate contract (schema v1)

Every potential durable learning becomes a **candidate** first. Agent
output is never automatically truth (INV-04).

```json
{
  "schema_version": 1,
  "candidate_id": "kc_<26 hex chars>",
  "project": "ai-native-dev-stack",
  "scope": {"repository": true, "module": null, "agent": null,
             "visibility": "project"},
  "kind": "PROJECT_RULE",
  "claim": "Integration tests must use the real test database.",
  "source": {"type": "session_observation", "session_id": "...",
             "agent": "claude", "timestamp": "..."},
  "evidence": [],
  "confidence": 0.0,
  "status": "PENDING",
  "target_hint": "AGENTS.md"
}
```

Kinds: `USER_PREFERENCE PROJECT_RULE MODULE_INVARIANT
ARCHITECTURE_DECISION FAILURE_PATTERN RESEARCH_KNOWLEDGE
INCIDENT_KNOWLEDGE WORKFLOW_RULE SESSION_ONLY WORKING_STATE DERIVED_FACT
UNKNOWN`. Target mapping follows the plan (PROJECT_RULE to `AGENTS.md`,
MODULE_INVARIANT to the owning `AI_CONTEXT.md`, ARCHITECTURE_DECISION to
an ADR, FAILURE_PATTERN to `KNOWN_FAILURE_PATTERNS.md`, research/incident
kinds to Vault `research/`/`incidents/`, SESSION_ONLY/WORKING_STATE to
transient, DERIVED_FACT to regeneration).

States and legal transitions:

```text
PENDING -> CLASSIFIED | REJECTED | EXPIRED
CLASSIFIED -> NEEDS_EVIDENCE | DUPLICATE | CONFLICTING | READY_FOR_PROMOTION | REJECTED
NEEDS_EVIDENCE -> SUPPORTED | EXPIRED | REJECTED
SUPPORTED -> READY_FOR_PROMOTION | CONFLICTING | DUPLICATE | SUPERSEDED | REJECTED
CONFLICTING -> SUPPORTED | REJECTED | SUPERSEDED
DUPLICATE -> SUPERSEDED | REJECTED
READY_FOR_PROMOTION -> PROMOTED | REJECTED | SUPERSEDED | EXPIRED
PROMOTED -> (terminal) SUPERSEDED only via a new candidate
REJECTED | SUPERSEDED | EXPIRED -> (terminal)
```

Any other transition is refused with `KNOWLEDGE_BAD_TRANSITION`. Version
rule: `schema_version` unknown or newer than the reader is
`KNOWLEDGE_SCHEMA_UNKNOWN` — never silently reinterpreted.

## 3. Provenance contract

Minimum provenance per candidate: project, repository, agent/harness,
session, origin type, timestamp, source paths, Git commit/head,
dirty-tree status. Optional: PR, issue, work contract, verification run,
user correction, MCP source, external source. Provenance answers where a
fact came from, what evidence supported it, which repository state was
observed, and which later knowledge superseded it. Vocabulary reuses the
Work Plane names (`git_recorded`, freshness outcomes) with a `knowledge.`
scope prefix; the knowledge package MUST NOT import
`ainative_workplane/` (ADR-0011 section 2) so Standard installs never
load an authority module.

## 4. Evidence model

Evidence types: `SOURCE_CODE TEST ADR AI_CONTEXT AGENTS_RULE KFP
GIT_HISTORY VERIFICATION_RUN USER_CONFIRMATION REPEATED_OBSERVATION
GRAPH_RELATION EXTERNAL_DOCUMENTATION`. Each item carries type, locator,
digest/reference, observed_at, repository state, confidence contribution.
Verification-run evidence is accepted ONLY as caller-supplied serialized
records (digests, identifiers); knowledge code never executes
verifications and never judges them. Scores are prioritisation aids, not
authority. Reinforcement appends evidence to one candidate; repetition
never duplicates the candidate.

## 5. Promotion rules

Operations: `ADD MERGE REFINE SUPERSEDE REJECT DEFER`. `CONFLICT` is a
candidate state, not an operation. Pipeline: resolve target, load
canonical current state, generate minimal patch, validate expected base
digest, apply transactionally (temp write, validate, atomic replace via
the `statelib.write_atomic` pattern), validate the resulting document,
record the Git diff. Target moved since evaluation: `STALE_BASE`, abort.
Two agents racing on one target: first commit wins, second gets
`PROMOTION_CONFLICT` and re-evaluates. Approval policy: `AGENTS.md` and
ADR targets always require a human; KFP requires a human until a later
ADR says otherwise; `AI_CONTEXT.md` auto-promotion is forbidden for now;
session archive and working state are automatic; research drafts are
automatic but never marked canonical.

## 6. Failure semantics (safe failure, INV-08)

Ambiguity: do not promote. Conflict: report, do not auto-resolve.
Unknown ownership: do not modify. Semantic retrieval unavailable: fall
back to deterministic sources with a degraded-mode status. Index
corruption: rebuild derived state. Crash mid-promotion: the old valid
file or the new one, never between (atomic replace; audit event
reconciled on recovery). Audit log (`audit.jsonl`) is lifecycle metadata,
not a knowledge store.

## 7. Provider architecture

```text
VaultProvider SemanticProvider GraphProvider GitProvider RepositoryProvider
```

All providers are capability-detected, optional, and behind one narrow
interface each (`available`, `version`, `freshness`, plus
`neighbours`/`lookup`/`graph path` as applicable). No critical workflow
fails because Smart Connections, Graphify or the Vault is absent:
deterministic context (`AGENTS.md`, nearest `AI_CONTEXT.md`,
`AI_SUMMARY.md`, referenced ADRs) always works. Retrieval order is
deterministic first, structural (Graphify callers/callees/blast radius)
second, semantic recall third, then rank (authority beats similarity),
then bound (hard budgets on notes, bytes, tokens, excerpts, neighbours —
rank harder, never inject everything). Active recall: semantic retrieval
runs only on explicit recall intent or insufficient deterministic
context, never on every prompt.

## 8. Scopes and multi-agent isolation

Scopes: `global repository project domain module agent private team`.
Every candidate records its originating harness
(`claude codex opencode gemini cursor`). Agent observations NEVER become
global facts automatically; promotion changes scope explicitly.
Cross-harness imports enter as candidates via preview-first
(`import --preview` mandatory before `--apply`), never directly canonical.

## 9. Staleness, retention, reset

Promoted items keep dependency refs (source paths, graph nodes, ADR
links). Code/graph/ADR changes mark dependents `POTENTIALLY_STALE` and
raise review candidates — never auto-rewrite. Decay affects retrieval
priority only (none for invariants/ADRs/safety rules; weak for failure
patterns/conventions; strong for status/observations/working memory).
Transient and derived state carry `max age / entries / bytes /
checkpoints`; canonical knowledge is never garbage-collected.
`reset-derived --dry-run` previews; `reset-derived` plus `rebuild` MUST
preserve canonical Markdown, Vault notes, Git history, ADRs, KFP,
`AI_CONTEXT`, `AGENTS` and audit provenance.

## 10. CLI and skills surface (authoritative: CLI)

```text
ainative knowledge status | capture | candidates | inspect <id>
  | verify <id> | promote <id> | reject <id> | conflicts
  | consolidate | stale | rebuild | reset-derived | import
ainative context checkpoint | ainative context restore
```

Skills (`/knowledge`, `/context`, `/learn`, `/verify-ai-docs`) delegate
to the CLI. Hooks stay minimal (SessionStart validate/restore,
PreCompact checkpoint, SessionEnd archive/capture, PostEdit fast
freshness only). Fast path (edit to minimal freshness) never runs model
or semantic work; deep path (consolidate, verify-ai-docs, CI) is manual
or session-end advisory. Consolidation stages: COLLECT, CLUSTER, VERIFY,
PROMOTION REVIEW — advisory output only (`ADD MERGE SUPERSEDE REJECT
NEEDS_HUMAN`).