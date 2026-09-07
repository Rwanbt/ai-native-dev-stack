# K0-B1 — Capture & Control Freeze Contract

**Repository:** `Rwanbt/ai-native-dev-stack`
**Status:** `GO / FROZEN`
**Purpose:** Freeze the contracts required before K1 — Explicit Capture + Measurement.
**Normative scope:** candidate/control schemas, identity, persistence safety, quarantine, measurement.
**Out of scope:** ContextPlanner, semantic retrieval, canonical promotion, Verified trust execution.

---

## 1. Architectural invariants

1. Canonical engineering knowledge remains human-readable Markdown/Git.
2. Candidate/control state is not canonical knowledge.
3. Local candidate payload is non-portable and purgeable.
4. Project Audit Control is portable lifecycle metadata, not knowledge truth.
5. Agent output cannot directly change authoritative state.
6. No hidden canonical SQLite/vector database.
7. Existing lifecycle/path/locking primitives are reused when present.
8. Any primitive marked `PARTIAL` by K0-A must be completed as a shared primitive, not duplicated locally.

---

## 2. State classes relevant to B1

B1 freezes the four architectural state classes:

```text
Canonical Knowledge
Transient Working State
Derived State
Durable Control State
```

Durable Control is split into:

```text
Local Control Payload
Project Audit Control
```

### Local Control Payload

Canonical conceptual path:

```text
.ai-native/state/knowledge/
```

Properties:

```text
MUST be ignored by Git
MUST be bounded
MUST be purgeable
MUST be secret-scanned
MUST NOT be required for fresh-clone audit
```

May contain:

```text
raw candidate text
temporary support
untrusted excerpts
draft mutation
working provenance
```

### Project Audit Control

Canonical conceptual path:

```text
.ai-native/audit/knowledge/
```

Properties:

```text
MUST NOT be Git-ignored
MUST survive reset-derived
MUST use versioned schemas
MUST NOT contain raw prompt/session content
MUST NOT contain raw retrieved note bodies
MUST NOT contain secret-bearing support
```

---

## 3. Repository reality gate

K0-A found:

```text
.ai-native/ is not ignored
```

Therefore B1 implementation MUST mechanically enforce both directions before persistence:

```text
.ai-native/state/knowledge/ → ignored
.ai-native/audit/knowledge/ → not ignored
```

Failure:

```text
CONTROL_PATH_POLICY_INVALID
```

No Local Control write may proceed while the local-control path is stageable.

---

## 4. Candidate schema

Candidate records MUST be versioned.

Minimum fields:

```text
schema_version
candidate_id
kind
state
created_at
updated_at
source
scope
claim
identity_key
identity_key_grammar_version
assertion_hash
assertion_normalization_version
hash_algorithm
provenance
```

Raw claim content belongs only in Local Control Payload.

Portable audit records contain only safe structured metadata.

---

## 5. Candidate state machine

Normative states:

```text
PENDING
IDENTITY_UNCONFIRMED
NEEDS_SUPPORT
REVIEWABLE
CONFLICTING
DUPLICATE
APPROVED
PROMOTION_IN_PROGRESS
APPLIED_PENDING_COMMIT
PROMOTION_FAILED
REJECTED
SUPERSEDED
RETRACTED
```

B1 freezes the vocabulary and legality model.

Mutation-specific transitions involving:

```text
APPROVED
PROMOTION_IN_PROGRESS
APPLIED_PENDING_COMMIT
PROMOTED
PROMOTION_FAILED
```

are implemented only under B3/K5.

### State authority

Only deterministic runtime events may transition candidate state.

Forbidden:

```text
LLM output directly sets state
provider result directly sets state
retrieved note directly sets state
```

Violation:

```text
ILLEGAL_STATE_TRANSITION
```

---

## 6. identity_key — root-specific grammar

Generic `<root>/<scope>/<concept>` grammar is forbidden.

### Module

```text
module/<module-id>/<namespace>/<property>[/<sub-property>...]
```

`module-id` MUST resolve to a known module.

### Project

```text
project/<project-slug>/<namespace>/<property>[/<sub-property>...]
```

`project-slug` MUST exactly equal the registered active project.

### Repository

```text
repo/<area>/<namespace>/<property>[/<sub-property>...]
```

`area` MUST resolve through `RepoAreaRegistry`.

Initial registry SHOULD remain small, for example:

```text
build
ci
docs
release
security
testing
tooling
workflow
dependencies
```

### Global/shared

```text
global/<shared-root-id>/<namespace>/<property>[/<sub-property>...]
```

`shared-root-id` MUST resolve to an explicitly configured shared root.

---

## 7. Identity vocabulary

Semantic segments cannot be arbitrary user text.

They MUST come from:

```text
versioned engineering vocabulary
OR
existing confirmed structured-claim vocabulary
```

Forbidden:

```text
customer names
secret-bearing identifiers
raw user sentences
unbounded model-generated taxonomy
```

---

## 8. Identity validation pipeline

Normative order:

```text
model/user proposal
↓
parse root
↓
root-specific shape validation
↓
scope resolution
↓
registry validation
↓
engineering-vocabulary validation
↓
character/length bounds
↓
audit-safety validation
↓
developer confirmation
↓
persist
```

Failure:

```text
IDENTITY_KEY_INVALID
```

No free-form fallback.

---

## 9. Assertion normalization

Before hashing, structured assertions use deterministic canonical JSON.

Conceptual form:

```json
{
  "identity_key": "module/payment/retry/max-attempts",
  "scope": "module/payment",
  "value": {
    "type": "integer",
    "value": 3
  }
}
```

Normative hash domain:

```text
SHA-256(
  "ainative-knowledge-assertion:v1\0"
  + canonical-json(structured-assertion)
)
```

Persist:

```text
assertion_normalization_version
hash_algorithm
```

No LLM fuzzy normalization in the authoritative hash path.

---

## 10. Rejection tombstones

Rejection applies to:

```text
assertion_hash
```

not merely `identity_key`.

Same exact assertion:

```text
→ prior rejection recognized
```

Different assertion under same identity:

```text
→ new reviewable candidate
```

Tombstones MUST NOT contain raw candidate text.

---

## 11. Secret quarantine

Before any untrusted persistence:

```text
size bounds
↓
secret scan
↓
source/path validation
↓
untrusted envelope
↓
persist
```

Production-safe behaviour:

```text
scanner unavailable
→ persistence refused
```

Applies to:

```text
candidate text
structured values
support
rejection reason
audit-safe fields
```

No manual bypass may count toward production qualification.

---

## 12. Candidate storage bounds

K1 implementation MUST define configurable bounds for:

```text
max candidate payload
max support payload
max candidate count
max audit-event count
max total Local Control storage
retention window
warning threshold
```

Exceeded single-candidate bound:

```text
CANDIDATE_TOO_LARGE
```

No unbounded growth.

---

## 13. Concurrency requirement

K0-A showed lifecycle locking exists but Knowledge does not use it.

Before enabling concurrent candidate capture, B1 implementation MUST provide:

```text
inter-process serialization
reload-under-lock
write
atomic replace / append
durability semantics
```

The current last-writer-wins append model is NOT acceptable for multi-agent capture.

Required property:

```text
N concurrent unique appends
→ N durable unique candidates
→ zero silent loss
```

Until this property is implemented and tested:

```text
AUTO_CAPTURE_CONCURRENCY = DISABLED
```

---

## 14. Durable control envelope

Common portable envelope:

```json
{
  "schema_version": 1,
  "record_type": "...",
  "record_id": "...",
  "payload": {}
}
```

Unknown future schema:

```text
→ fail closed
```

No silent interpretation.

---

## 15. Measurement contract

Before K1 measurement begins, commit:

```text
metric
numerator
denominator
minimum observation window
FULL threshold
NARROW threshold
STOP threshold
```

Changing thresholds after seeing data requires a versioned decision.

The initial decision branches are:

```text
FULL
NARROW
STOP
```

Exact numeric thresholds MUST be baseline-driven.

Existing Jaccard/sufficiency constants remain experimental defaults until benchmarked.

---

## 16. Substantive session

A session counts only when objective engineering activity occurs, e.g.:

```text
repository mutation
verification/test execution
architecture investigation
explicit project learning
```

Pure greetings/status-only sessions do not count.

Prefer deterministic telemetry over model classification.

---

## 17. B1 CLI surface

Initial supported surface SHOULD stay small:

```text
ainative knowledge status
ainative knowledge learn
ainative knowledge candidates
ainative knowledge inspect
ainative knowledge reject
```

Internal transition/debug commands may exist but MUST NOT grant canonical authority.

Promotion commands belong to B3/K5.

---

## 18. B1 mandatory tests

At minimum:

```text
E2E-D   secret claim rejected
E2E-E   secret support rejected
E2E-F   local state ignored + project audit not ignored
E2E-Y   scanner unavailable → persistence refused
E2E-AL  root-specific identity validation
E2E-O   rejection tombstone recognized
E2E-P   changed assertion remains reviewable
E2E-Q   future schema fails closed
E2E-AI  model cannot perform illegal state transition
```

Plus concurrency:

```text
multiple concurrent candidate writers
→ no lost update
```

Property tests:

```text
state-machine legality
identity grammar
canonical JSON stability
assertion hash determinism
schema compatibility
storage bounds
```

---

## 19. B1 freeze gate

B1 is implementation-ready only when:

```text
schemas finalized
identity grammar implemented
assertion normalization implemented
secret quarantine fail-closed
.gitignore policy bidirectional
candidate state machine deterministic
candidate persistence concurrency-safe for claimed usage
measurement contract committed
tests assigned/passing
```

---

## 20. B1 status

```text
ARCHITECTURE: FROZEN
CURRENT BRANCH IMPLEMENTATION: PARTIAL / MUST BE DELTA-RECONCILED
NEXT FUNCTIONAL PHASE: K1 after K0-A/B1 evidence reconciliation
```