# K0-B3 — Mutation & Trust Freeze Contract

**Repository:** `Rwanbt/ai-native-dev-stack`
**Status:** `GO / FROZEN SPECIFICATION`
**Purpose:** Freeze canonical mutation, Git representation, audit, trust, recovery and representation-health contracts before K5.
**Execution gate:** K5 remains CONDITIONAL on K1–K4 measurements (`STOP / NARROW / FULL`).
**Current profile from K0-A:** `TRUST_BOUNDARY_NOT_SEPARATED`; Work Plane trust root `.ai-native/trust/project_trust.json` is readable/writable by controlled actor → `UNSAFE` for production trust.

---

## 1. K5 is conditional

B3 being frozen does NOT authorize K5 implementation/merge.

Execution order:

```text
K1 capture + measurement
K2 ContextPlanner
K3 continuity
K4 support/conflict/dedup
↓
measure value
↓
STOP / NARROW / FULL
↓
K5 only if justified
```

Baseline K5 must beat:

```text
agent edits canonical Markdown
+
developer reviews Git diff
```

Current promotion runtime stays quarantined as:

```text
STANDARD / UNVERIFIED
```

until K5 gate authorizes further integration.

---

## 2. Initial canonical targets

If K5 is authorized, initial automated/assisted targets are limited to:

```text
AI_CONTEXT controlled sections
KFP append/deprecate/supersede
```

Not automated initially:

```text
AGENTS
ADR
Vault
AI_SUMMARY
```

`AI_SUMMARY` is never a promotion target.

Vault lifecycle mutation remains forbidden initially.

---

## 3. Target ownership

Knowledge target ownership categories:

```text
USER_OWNED
STACK_MANAGED
GENERATED
EXTERNAL_PROVIDER
READ_ONLY
CONTROL_LOCAL
CONTROL_AUDIT
```

These MUST map explicitly to existing lifecycle ownership classes.

Do not merge the two taxonomies.

Mutation policy is derived from target ownership.

---

## 4. Target mutation policy

### AI_CONTEXT

```text
controlled sections only
minimal patch
section-level base digest
section-level result digest
post-write validation
```

### KFP

```text
append
deprecate
supersede
preserve historical entries
```

### ADR

```text
manual/high-authority only
```

### AGENTS

```text
manual/high-authority only
```

### Vault

```text
READ_ONLY from Knowledge Lifecycle
```

---

## 5. Approval model — three orthogonal concepts

### approval_mode

```text
TRUSTED_OPERATOR_CEREMONY
VERIFIED_WORKPLANE_AUTHORITY
EXTERNAL_ATTESTATION
```

### capability_status

```text
SEPARATED
NOT_SEPARATED
UNKNOWN
```

### evidence_status

```text
UNVERIFIED_CEREMONY
VERIFIED_WORKPLANE_AUTHORITY
EXTERNALLY_ATTESTED
```

These dimensions MUST NOT be collapsed.

---

## 6. QUAL-T semantics

QUAL-T answers only:

> Is the Knowledge Lifecycle approval action exposed to the controlled-agent execution profile?

Current K0-A result:

```text
TRUST_BOUNDARY_NOT_SEPARATED
```

Therefore current profile:

```text
capability_status = NOT_SEPARATED
```

This is evidence, not architecture speculation.

QUAL-T does NOT prove repository-resident approval evidence is non-forgeable.

---

## 7. Standard ceremony

Standard ceremony is always:

```text
approval_mode = TRUSTED_OPERATOR_CEREMONY
evidence_status = UNVERIFIED_CEREMONY
```

It may produce:

```text
PROMOTED
HEALTHY
UNVERIFIED
```

but MUST NOT claim:

```text
TRUST_ENFORCED
PRODUCTION_QUALIFIED_TRUST
VERIFIED_APPROVAL
```

Current branch promotion is therefore STANDARD/UNVERIFIED.

---

## 8. Production trust qualification

Production-trusted approval requires:

```text
evidence_status in {
  VERIFIED_WORKPLANE_AUTHORITY,
  EXTERNALLY_ATTESTED
}
```

NOT:

```text
capability_status == SEPARATED
```

Capability separation is defence-in-depth, not authenticity.

---

## 9. Work Plane authority reuse

Preferred production path:

```text
Knowledge Lifecycle
↓
existing Verified Work Plane project trust authority
↓
authenticated approval evidence
```

Knowledge Lifecycle MUST NOT create:

```text
second trust root
second PKI
second signer hierarchy
second authority DB
```

If reusable verifier API is partial:

```text
extract/complete shared primitive
```

Do not copy authority logic.

---

## 10. Trust-root accessibility

A Work Plane authority can qualify Knowledge Lifecycle trust only if its root/signing material is unavailable to the controlled actor.

K0-A current reality:

```text
.ai-native/trust/project_trust.json
→ readable by controlled actor
→ writable by controlled actor
→ no signer configured
→ UNSAFE
```

Therefore in the current mono-user profile:

```text
VERIFIED_WORKPLANE_AUTHORITY
CANNOT qualify production trust
```

until the trust root/signing material is made inaccessible/non-forgeable relative to the controlled actor.

This is a deployment/security prerequisite, not something Knowledge Lifecycle may paper over.

---

## 11. Authority reference binding

A valid authority object alone is insufficient.

Required:

```text
authority_ref valid
AND
authority evidence binds exact approval_digest
AND
approval_digest binds:
  decision_id
  assertion_hash
  target
  operation
  scope
  base_digest
  intended_result_digest
```

Otherwise:

```text
APPROVAL_AUTHORITY_INVALID
trust_qualification = INVALID
```

No replay/cross-approval acceptance.

---

## 12. Trust qualification

Derived statuses:

```text
VERIFIED_WORKPLANE
EXTERNALLY_ATTESTED
UNVERIFIED
INVALID
```

Independent from:

```text
candidate lifecycle state
representation health
```

Example:

```yaml
lifecycle_state: PROMOTED
representation_health: HEALTHY
trust_qualification: UNVERIFIED
```

---

## 13. Promotion approval binding

Approval MUST bind exact mutation intent:

```text
decision_id
assertion_hash
target
operation
scope
base_digest
intended_result_digest
```

Any change invalidates approval.

Result:

```text
→ REVIEWABLE
→ no canonical mutation
```

---

## 14. Existing transaction engine reuse

Reuse/adapt `ainative.lifecycle`.

No second transaction engine.

Lifecycle transaction states remain:

```text
PREPARED
APPLYING
COMMITTED
ROLLED_BACK
INTERRUPTED
```

Candidate lifecycle states remain separate.

K0-A found lifecycle locking exists; Knowledge mutation MUST reuse or extract it rather than invent another lock implementation.

---

## 15. Promotion transaction

Normative sequence:

```text
1. candidate APPROVED
2. validate target ownership
3. validate path confinement
4. validate approval/trust
5. validate repository/base state
6. acquire target/local mutation lock
7. re-read base under lock
8. transaction PREPARED
9. transaction APPLYING
10. apply canonical mutation
11. verify result digest
12. prepare immutable minimal audit receipt
13. create Git representation
14. verify commit/tree/result using same resolver semantics as reconcile
15. transaction COMMITTED
16. candidate PROMOTED
```

---

## 16. Path confinement

Reuse existing shared confinement primitive.

Reject:

```text
..
absolute paths
Windows drive escape
UNC
NUL
symlink escape
junction escape
repo-root escape
```

No Knowledge-specific duplicate resolver.

---

## 17. APPLIED_PENDING_COMMIT

Meaning:

> Approved canonical mutation exists locally, but required Git representation has not yet been observed.

Transitions:

```text
matching commit
→ PROMOTED

target reverted
→ PROMOTION_FAILED

target changed incompatibly
→ REVIEWABLE
```

Another mutation touching the same controlled target must reconcile first.

---

## 18. Project Audit promotion receipt

Promotion receipt is immutable.

Minimum conceptual fields:

```text
schema_version
record_type
record_id
transaction_id
candidate_decision_id
target
controlled_section_identity
operation
base_digest
result_digest
approval_digest
approval_mode
capability_status
evidence_status
authority_ref if required
timestamp
```

Must NOT contain:

```text
raw candidate
raw support
raw prompt
secret-bearing data
own Git commit SHA
```

---

## 19. One-commit protocol

Initial protocol:

```text
one Git commit
```

introduces:

```text
canonical target result
+
immutable promotion receipt
```

Receipt MUST NOT contain its own commit SHA.

---

## 20. promotion_commit_ref

`promotion_commit_ref` is a derived Git property, never serialized inside its own receipt.

Definition:

```text
the unique reachable Git commit that:
1. first introduces the immutable receipt identified by record_id/path
AND
2. contains the expected promoted controlled-section/result digest
```

Results:

```text
exactly one → promotion_commit_ref
zero        → REPRESENTATION_MISSING
multiple    → REPRESENTATION_AMBIGUOUS → fail closed
```

No machine-local durable association required.

---

## 21. Git primitive reuse

K0-A found Git provenance primitives are PARTIAL:

```text
recording_commit
blob_at_commit
commit_count
```

B3 implementation MUST:

```text
reuse/adapt/extract a shared generic resolver
```

for:

```text
introduction commit
tree/blob at commit
path history
```

No separate Work Plane vs Knowledge algorithms.

---

## 22. Rebase / squash stability

Durable promotion identity:

```text
receipt record_id
+
result_digest
```

not old SHA.

After history rewrite, resolver derives the valid current reachable introduction commit.

Fresh clone must reconstruct representation health with:

```text
Git history
canonical files
Project Audit records
```

No Local Control dependency.

---

## 23. Receipt immutability

Historical promotion receipts MUST NOT be rewritten by migration.

Use separate:

```text
migration_record
correction_record
retraction_record
```

Receipt path/record identity handling MUST remain deterministic across future migrations.

---

## 24. Section-level result identity

For section-controlled files like `AI_CONTEXT.md`:

```text
result_digest = promoted controlled section/result digest
```

not whole-file digest.

Unrelated edit outside controlled section:

```text
→ health remains HEALTHY
```

This behaviour is already proven by current E2E-AY and MUST be preserved.

---

## 25. Representation health

Derived values:

```text
HEALTHY
REVERTED
SUPERSEDED
MISSING
AMBIGUOUS
```

### HEALTHY

Receipt reachable and promoted controlled semantic unit still matches result digest.

### REVERTED

History shows explicit reversion/removal of promoted semantic unit.

### SUPERSEDED

Receipt remains reachable and a later legitimate canonical change replaced the promoted controlled semantic unit with another valid state.

External Git edit may count as supersession if deterministic continuity is established.

### MISSING

Required continuity cannot be established.

### AMBIGUOUS

Multiple incompatible valid resolution paths exist.

Fail closed.

---

## 26. Historical promotion vs current health

Historical:

```text
candidate PROMOTED
```

means promotion succeeded at time T.

Current health is calculated separately.

Valid combination:

```text
historical PROMOTED
current SUPERSEDED
```

Never rewrite historical promotion event merely to reflect present repository health.

---

## 27. Reconcile boundary

`ainative knowledge reconcile` MUST NOT become a second transaction-recovery engine.

Order:

```text
1. invoke/reuse lifecycle interrupted-transaction recovery
2. inspect receipt ↔ Git representation
3. inspect receipt ↔ target/section
4. inspect decision ↔ receipt
5. derive representation_health
6. derive trust_qualification
```

---

## 28. Remote/multi-clone scope

Initial support:

```text
LOCAL
REPOSITORY_WITH_UPSTREAM
```

Not distributed multi-writer collaboration.

Before upstream publication:

```text
fetch/revalidate remote
```

Divergence/unknown remote base:

```text
REMOTE_DIVERGED
REMOTE_BASE_UNVERIFIED
```

fail closed.

No distributed lock service in initial architecture.

---

## 29. Artifact growth budgets

Promotable artifacts MUST have configurable budgets.

Exceeded:

```text
PROMOTION_BUDGET_EXCEEDED
```

Maintenance actions:

```text
DEPRECATE
ARCHIVE
RETRACT
SUPERSEDE
```

No infinite KFP/AI_CONTEXT growth.

---

## 30. B3 mandatory tests

### Approval/trust

```text
E2E-AK  approval mutation changes → approval invalid
E2E-AU  forged verified receipt without valid authority → INVALID
E2E-AV  ceremony-only → PROMOTED/HEALTHY/UNVERIFIED
E2E-AW  valid Work Plane authority on fresh clone → VERIFIED_WORKPLANE
E2E-AX  forged/replayed authority_ref → INVALID
```

### Git/transaction

```text
E2E-K   local concurrent promotions conflict safely
E2E-L   diverged upstream refused
E2E-M   interrupted transaction recovers
E2E-Z   Git commit succeeded before journal finalization → recovery forward
E2E-AF  required audit record missing → inconsistency
E2E-AQ  fresh clone resolves promotion
E2E-AR  rebase/squash resolves rewritten introduction commit
E2E-AS  receipt migration leaves historical receipt immutable
E2E-AT  ambiguous Git representation fails closed
```

### Representation health

```text
E2E-AY
edit outside controlled section → HEALTHY
later legitimate controlled-section replacement → SUPERSEDED
```

### Trust-root security

New production qualification test:

```text
controlled actor can read/write/invoke claimed Work Plane trust root/signer
→ authority marked UNSAFE
→ VERIFIED_WORKPLANE trust qualification forbidden
```

---

## 31. Current K0-A result impact

Current profile:

```text
QUAL-T = TRUST_BOUNDARY_NOT_SEPARATED
Work Plane root = UNSAFE
signer = absent
```

Therefore the only valid current promotion assurance is:

```text
STANDARD / UNVERIFIED
```

Any runtime currently returning stronger assurance must be considered incorrect.

---

## 32. K5 gate

B3 implementation may be prepared, but canonical promotion does not enter mainline product flow until measurements choose:

```text
NARROW
or
FULL
```

If decision is:

```text
STOP
```

retain:

```text
explicit capture
ContextPlanner
continuity
support/conflict/dedup
```

and leave promotion machinery non-product/experimental.

Stopping is a successful outcome.

---

## 33. B3 freeze gate

B3 is implementation-ready when:

```text
target ownership mapped
mutation policies exact
approval binding exact
trust model exact
trust-root accessibility checked
authority-ref binding exact
transaction reuse specified
lock reuse specified
path confinement reuse specified
one-commit receipt protocol frozen
promotion_commit_ref resolver frozen
receipt immutability frozen
section-level result identity frozen
representation health frozen
reconcile boundary frozen
remote revalidation frozen
artifact budgets frozen
mandatory E2E assigned
```

---

## 34. B3 status

```text
ARCHITECTURE: FROZEN SPECIFICATION

CURRENT PROFILE:
  capability_status = NOT_SEPARATED
  Work Plane trust root = UNSAFE
  production-trust qualification unavailable

CURRENT PROMOTION RUNTIME:
  STANDARD / UNVERIFIED
  QUARANTINED FROM PRODUCTION CLAIMS

K5:
  CONDITIONAL
```