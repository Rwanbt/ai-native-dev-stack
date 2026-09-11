# K0-B2 — Context & Authority Freeze Contract

**Repository:** `Rwanbt/ai-native-dev-stack`
**Status:** `GO / FROZEN`
**Purpose:** Freeze the contracts required before K2 — Unified Bounded ContextPlanner.
**Normative scope:** authority, context ownership, provider isolation, structured claims, context budgets.
**Out of scope:** canonical mutation and production trust.

---

## 1. Core invariant — one ContextPlanner

There MUST be exactly one owner of context selection:

```text
ContextPlanner
```

All context-producing surfaces become adapters:

```text
assemble_context.py
CLI retrieval
skills
harness adapters
future active recall
```

No second ranking/injection engine is allowed.

K0-A found the existing assemble path has one caller; B2 implementation MUST preserve that simplicity and route it through ContextPlanner rather than create parallel selection logic.

---

## 2. Context processing pipeline

Normative sequence:

```text
deterministic applicable sources
↓
scope validation
↓
freshness validation
↓
relevance ranking
↓
typed authority resolution
↓
conflict/drift evaluation
↓
tier assignment
↓
budget enforcement
↓
optional active recall
↓
final context bundle
```

Authority and relevance are separate.

---

## 3. Typed authority domains

Minimum domains:

```text
ENGINEERING_POLICY
ARCHITECTURE_DECISION
IMPLEMENTATION_FACT
MODULE_CONSTRAINT
BEHAVIOURAL_EVIDENCE
FAILURE_PREVENTION
INFORMATIVE_RESEARCH
HISTORICAL_OBSERVATION
UNTRUSTED
```

Typical mapping:

```text
AGENTS                  → ENGINEERING_POLICY
accepted ADR            → ARCHITECTURE_DECISION
source code             → IMPLEMENTATION_FACT
AI_CONTEXT              → MODULE_CONSTRAINT
tests                   → BEHAVIOURAL_EVIDENCE
KFP                     → FAILURE_PREVENTION
research                → INFORMATIVE_RESEARCH
session note            → HISTORICAL_OBSERVATION
candidate               → UNTRUSTED
generated summary       → DERIVED, no authority by itself
```

---

## 4. Scope precedence

Within the same authority domain:

```text
module
>
project
>
repository
>
global/shared
```

Visibility/private status is orthogonal to authority.

Private memory does not become shared authority.

---

## 5. Task intent is advisory

Task intent may:

```text
reorder
change presentation emphasis
select explanation focus
```

It MUST NOT:

```text
remove applicable normative sources
hide drift
downgrade higher authority
```

Example:

```text
ADR says retry = 3
code implements retry = 5
```

For "what does the software do?":

```text
implementation fact 5 shown prominently
architecture decision 3 retained
DRIFT = true
```

---

## 6. Restricted source views

Restricted authority views may be requested only by trusted control fields:

```text
CLI flag
trusted API field
trusted configuration
```

Never by:

```text
natural-language task prompt
Vault note
semantic result
LLM inference
```

Example valid control:

```text
--source-view=implementation-only
```

---

## 7. Context tiers

### Tier A — Mandatory

Applicable:

```text
engineering policy
module constraints
critical prohibitions
relevant architectural requirements
```

Cannot be silently evicted.

### Tier B — Working continuity

```text
current task
plan
checkpoint
files touched
blockers
```

### Tier C — Structural

```text
Graphify/code relationships
dependency neighborhood
blast radius
```

### Tier D — Semantic/historical

```text
Vault recall
research
past sessions
semantic neighbors
```

Most expendable.

---

## 8. Mandatory context overflow

If applicable Tier A exceeds the harness usable context:

```text
MANDATORY_CONTEXT_OVERFLOW
```

No automatic:

```text
LLM summarization
mandatory-source omission
secondary authoritative compact copy
```

No `--exclude-mandatory-source` escape hatch in the initial architecture.

Resolution is structural:

```text
reduce policy bloat
split canonical playbooks
improve source scoping
use a harness with sufficient capacity
```

---

## 9. Negative knowledge

Knowledge type may include:

```text
PRESCRIPTIVE
PROHIBITIVE
CONDITIONAL
DESCRIPTIVE
HISTORICAL
```

Applicable prohibitions/KFP rules are Tier A.

Semantic ranking cannot silently eject them.

---

## 10. Active recall

Do not semantic-search every prompt.

Flow:

```text
deterministic context
↓
is recall needed?
↓
Graphify / SemanticProvider
```

Possible triggers:

```text
explicit recall request
unknown identifier
historical question
insufficient deterministic context
research/reference request
```

Measure escalation frequency.

---

## 11. Provider interfaces

Core conceptual providers:

```text
RepositoryProvider
VaultProvider
SemanticProvider
GraphProvider
GitProvider
```

Semantic provider contract:

```text
capabilities()
search(query, scope, limit)
health()
```

Provider metadata includes:

```text
execution_scope
data_egress
project_filtering
authority_ceiling
```

---

## 12. Provider authority ceiling

Provider results cannot self-assign authority.

Example:

```text
result claims ENGINEERING_POLICY
configured ceiling = INFORMATIVE_RESEARCH
→ final authority <= INFORMATIVE_RESEARCH
```

Provider metadata is data, not authority.

---

## 13. Vault role

Vault is optional.

When configured, Vault Markdown may be canonical only for explicitly Vault-scoped project knowledge.

Initial lifecycle:

```text
read/search = allowed
canonical write = forbidden
```

No lifecycle-driven Vault mutation without a future dedicated protocol.

---

## 14. Semantic provider / Smart Connections

Smart Connections may implement `SemanticProvider`.

Core MUST function without it.

Failure:

```text
deterministic ContextPlanner still operates
semantic enrichment degrades
doctor reports provider health
```

No mandatory semantic backend.

---

## 15. Graphify role

Graphify may implement `GraphProvider`.

Used for:

```text
structural neighborhood
dependency context
blast radius
staleness support
retrieval ranking
```

Graphify output is derived state.

Absence is graceful degradation.

---

## 16. Project isolation

Every retrieved source MUST resolve physically to the active project scope.

A result with forged metadata is insufficient.

Required:

```text
resolve real path
verify configured project root
verify project registry/scope
```

If physically outside active project:

```text
DROP
```

Unknown/unresolved scope:

```text
DROP
```

---

## 17. Shared/global scope

Explicit configuration only:

```text
project_root
shared_roots[]
```

Global/shared content may be included only when:

```text
shared root configured
AND
trusted request/policy permits shared scope
```

No provider can make itself global.

---

## 18. Structured claims

Human-readable canonical content remains authority.

Structured claims are:

```text
validated deterministic indexes
```

not independent truth.

Each claim MUST bind:

```text
identity_key
structured_value
source_path
source_anchor
source_digest
claim_schema_version
```

---

## 19. Claim freshness

If canonical source changes and claim binding no longer matches:

```text
CLAIM_STALE
```

Stale claim:

```text
remains observable
cannot participate in deterministic conflict resolution
```

Validator checks:

```text
anchor exists
source digest matches
claim structure valid
identity grammar valid
scope resolvable
```

Failure:

```text
CLAIM_STALE
or
CLAIM_INVALID
```

---

## 20. Legacy Markdown

Existing prose without structured claims remains valid.

No:

```text
mass migration
paragraph IDs everywhere
hidden LLM canonicalization
```

Deterministic conflict guarantee applies only to confirmed structured identities.

Natural-language contradiction detection is advisory.

---

## 21. Drift/conflict behaviour

ContextPlanner MUST preserve relevant conflicting authoritative sources.

Example:

```text
ADR requirement
vs
implementation fact
```

Result:

```text
both retained
typed separately
drift surfaced
```

Never resolve by silent source deletion.

---

## 22. Derived summaries

Generated summaries such as `AI_SUMMARY.md` are derived.

If summary contradicts canonical source:

```text
canonical source wins
```

Summary cannot establish authority.

---

## 23. Context bundle output

ContextPlanner output SHOULD expose enough metadata for audit/debug:

```text
source
scope
authority_domain
tier
freshness
provider
reason_included
reason_dropped
conflict/drift flag
token/byte cost
```

No chain-of-thought.

---

## 24. B2 mandatory tests

```text
E2E-A    cross-project semantic result → DROP
E2E-B    forged project metadata outside root → DROP
E2E-C    retrieved injection cannot become instruction authority
E2E-AA   intent cannot hide normative drift
E2E-AB   unconfigured shared/global result → DROP
E2E-AC   configured shared/global result → capped inclusion
E2E-AD   provider cannot exceed authority ceiling
E2E-AM   source changes → claim stale
E2E-AN   natural-language restricted-view request ignored
E2E-R    legacy context entry point uses ContextPlanner
E2E-S    summary contradiction → canonical wins
E2E-V    Tier A overflow fails visibly
```

Additional invariant test:

```text
exactly one active context-selection owner
```

---

## 25. Performance measurement

Before hardening thresholds, measure:

```text
ContextPlanner p50/p95
context bytes/tokens
tokens per tier
semantic escalation rate
provider failure rate
Graphify overhead
relevant-context precision
```

Do not freeze arbitrary latency/token thresholds before baseline.

---

## 26. B2 doctor integration

`ainative doctor` SHOULD report:

```text
ContextPlanner active?
legacy adapter status
Vault capability
Graphify capability
SemanticProvider capability
claim freshness
cross-project isolation configuration
Tier-A health
```

Doctor remains diagnostic/informative, but production qualification MUST fail when a required invariant is unhealthy.

---

## 27. B2 freeze gate

B2 implementation-ready when:

```text
single ContextPlanner owner implemented
legacy caller routed through it
authority domains implemented
intent cannot suppress authority
provider ceilings implemented
project isolation enforced
shared roots explicit
claims source-bound and freshness-aware
Tier A-D implemented
MANDATORY_CONTEXT_OVERFLOW implemented
semantic/graph providers optional
mandatory E2E assigned/passing
```

---

## 28. B2 status

```text
ARCHITECTURE: FROZEN
CURRENT BRANCH retrieval.py/providers.py: LIKELY REUSABLE BUT MUST BE MAPPED TO THIS CONTRACT
NEXT FUNCTIONAL PHASE: K2 after B2 reconciliation
```