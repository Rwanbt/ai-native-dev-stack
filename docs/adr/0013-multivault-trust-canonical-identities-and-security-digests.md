# ADR-0013 — Multi-Vault trust, canonical identities, and security digests

- Status: proposed
- Date: 2026-09-11
- Alias: ADR-MV-001
- Materializes: Multi-Vault v2.5+FIX FROZEN SECURITY DESIGN and final freeze erratum.
- Constrains: future `ainative/context/`, `ainative/authority/`, `ainative/bind/`,
  Multi-Vault schemas, security digests, persistence namespace derivation,
  `RuntimeContextHandle`, `ImmutableAuthoritativeSecurityState`,
  `ResolvedSecurityContext`, `AllowedContextEnvelope`, and `project_security_id`.
- Does not modify: ADR-0001 through ADR-0012; the Verified Work Plane authority
  architecture; `docs/K0-B1-CAPTURE-CONTROL-FREEZE.md`;
  `docs/K0-B2-CONTEXT-AUTHORITY-FREEZE.md`;
  `docs/K0-B3-MUTATION-TRUST-FREEZE.md`.
- Security status: design frozen; implementation and production qualification pending.

## Context

The repository now has two already-frozen authority constraints that Multi-Vault must
consume rather than replace.

First, K0-B2 requires exactly one owner of context selection: `ContextPlanner`. Any
vault, semantic, graph, repository, memory or harness source introduced by Multi-Vault
must therefore become an allowed source or adapter. It must not create a second ranking
or injection engine.

Second, K0-B3 records the current execution profile as
`TRUST_BOUNDARY_NOT_SEPARATED`. Repository-local state that is writable by the
controlled same-OS-user process is not a production-trust root. Multi-Vault must
therefore distinguish a governed, useful `GUARDED` mode from genuinely isolated
`ENFORCED-*` modes instead of silently upgrading local policy files into non-forgeable
authority.

The Multi-Vault security review converged on a frozen design with the following core
properties:

- a vault is a trust/data boundary;
- descriptive context is not authority;
- runtime authorization is issued through opaque capabilities;
- each security domain has independent runtime authority;
- context exposure, memory policy and execution assurance scope persistence;
- canonical digests are cross-platform contracts, not implementation details;
- all security-relevant unknowns fail closed for sensitive classifications.

This ADR freezes the identities, capability model and canonical digest ownership needed
by MV-02 and later work.

## Decision

### 1. Security domain and classification

A Multi-Vault security domain represents one authorization/data boundary. At minimum it
binds:

```text
security_domain_id
vault_identity
checkout_identity
project_security_id
classification
operator_authority_binding
```

Supported classifications are:

```text
PERSONAL
TEAM
CONFIDENTIAL
CRITICAL
```

Classification is trusted policy. Repository content, natural-language prompts, vault
notes, semantic retrieval and harness output MUST NOT raise or lower it.

### 2. `ResolvedSecurityContext` is descriptive only

`ResolvedSecurityContext` may describe the current workspace, discovered vault,
classification, configured provider requirements and human-readable qualification
state.

It MUST NOT itself grant:

```text
filesystem access
vault access
memory access
provider/model authorization
Git authorization
MCP authorization
persistent-store access
```

A forged or edited projection therefore grants zero additional data access.

### 3. `RuntimeContextHandle` is the runtime capability

Privileged Multi-Vault operations require an opaque `RuntimeContextHandle`.

Normative properties:

```text
>= 128 bits CSPRNG entropy
opaque
non-persistent
session-scoped
security-domain-scoped
security-epoch-scoped
authority-instance-scoped
caller-identity-scoped
revocable
expires with the governed workload
```

Authorization lookup requires:

```text
handle
+
authenticated caller identity
+
authority instance identity
+
current security epoch
```

The raw handle alone is insufficient authority.

The handle MUST be redacted from ordinary string representations, logs, prompts,
transcripts, vault notes, crash reports and audit payloads. Implementations SHOULD use a
dedicated secret/capability type whose normal textual representation is `<redacted>`.

### 4. `ImmutableAuthoritativeSecurityState`

Each valid runtime handle resolves to one immutable authoritative snapshot containing at
least:

```text
security_domain_id
security_epoch
vault_identity
checkout_identity
project_security_id
classification
AllowedContextEnvelope
ApprovedModelEgress reference/digest
memory_policy_digest
persistence_assurance_digest
execution profile
runtime observation policy
authority instance identity
```

No mutable process-global "current vault", "current roots" or union of permissions is an
authority source.

### 5. `AllowedContextEnvelope`

`AllowedContextEnvelope` is the authoritative maximum set of context sources that may
be considered for a session. It contains typed roots/classes such as:

```text
repository_roots
vault_memory_roots
shared_memory_roots
semantic_roots
graph_roots
allowed_write_targets
project boundaries
source classes
```

The flow is:

```text
RuntimeContextHandle
→ Runtime Authority
→ AllowedContextEnvelope
→ source adapters/providers
→ ContextPlanner
```

`ContextPlanner` remains the sole owner of ranking, tiering, budget and injection.

### 6. Canonical encoding

All security digests defined here use one versioned canonical representation.

Preferred encoding:

```text
RFC 8785 JSON Canonicalization Scheme
```

or an exactly specified equivalent where a source value is not naturally JSON.

Before canonicalization:

- maps have defined key names and types;
- unordered sets are normalized to explicitly sorted arrays;
- filesystem identities are represented by typed normalized fields, never by arbitrary
  `repr()` output;
- paths use a documented logical/canonical form and never platform-dependent raw string
  hashing;
- byte sequences use a documented encoding;
- every digest input includes a schema version.

A digest implementation MUST NOT depend on Python object representation, insertion
order, locale or host-specific formatting.

### 7. Canonical digest ownership

The following eight digests are normative Multi-Vault contracts:

#### 7.1 `SecurityDomainIdentity`

Purpose: stable logical identity of the authorization/data domain.

Canonical input:

```text
{
  schema_version,
  security_domain_id,
  vault_logical_id,
  project_security_id,
  operator_authority_domain_id
}
```

It excludes mutable runtime data.

#### 7.2 `SecurityEpoch`

Purpose: revoke previously issued handles when authoritative security state changes.

Canonical input:

```text
{
  schema_version,
  security_domain_id,
  epoch_counter_or_nonce,
  authority_instance_generation
}
```

Changing an authorization-relevant binding MUST advance the epoch.

#### 7.3 `ContextExposureDigest`

Purpose: scope persistent state by the complete context surface that could be exposed.

Canonical input is the complete security projection of `AllowedContextEnvelope`,
including at least:

```text
repository/worktree roots
vault roots
shared roots
semantic roots
graph roots
derived persistable source classes
project boundaries
```

#### 7.4 `MemoryPolicyDigest`

Purpose: scope persistent state by the complete memory policy.

It hashes the full normalized memory-policy object, not a hand-maintained subset of
selected fields.

#### 7.5 `PersistenceAssuranceDigest`

Purpose: prevent silent reuse of memory produced under a different execution assurance.

Canonical input includes:

```text
effective_execution_profile
provider_egress_class
storage_assurance_class
```

V1 compatibility is exact-match only.

#### 7.6 `SemanticEgressDigest`

Purpose: detect security-relevant semantic/RAG configuration drift.

Its versioned schema MUST include every semantic configuration field whose change may
alter data egress, provider use, endpoint/routing or cross-project exposure.

#### 7.7 `ExecutionBoundaryDigest`

Purpose: bind `ENFORCED-*` qualification to measured boundary evidence.

The normalized input covers qualified evidence classes such as:

```text
network policy
mounts
filesystem/ACL boundary
credential boundary
harness config roots
runtime identity
IPC topology
REST reachability
authority-store placement
provider route policy
Git transfer boundary
process containment
```

The digest is valid only while its evidence remains fresh.

#### 7.8 `PushIntentDigest`

Purpose: bind one governed Git push authorization to the exact transfer intent.

The canonical input includes the security-relevant fields of the `PushIntent` defined
by ADR-0016, including exact refs, expected remote base, destination identity, transport
policy digest, candidate-object-set digest, scan result and expected Git identity.

### 8. Persistent-store namespace

Persistent Multi-Vault memory/state namespace is derived from:

```text
SecurityDomainIdentity
+
ContextExposureDigest
+
MemoryPolicyDigest
+
PersistenceAssuranceDigest
```

An old namespace MUST NOT be automatically loaded after a mismatch.

### 9. Assurance transitions

Both directions are explicit:

```text
GUARDED → ENFORCED-*
ENFORCED-* → GUARDED
```

Old state is quarantined/not auto-loaded until an explicit migration or downgrade
decision is recorded.

No "stronger before, therefore safe everywhere" inference is allowed.

### 10. `GUARDED` vs `ENFORCED-*`

`GUARDED` protects governed paths against accidental/stale configuration, wrong-domain
context and unsupported combinations. It does not claim protection from a hostile
same-OS-user actor that can rewrite local files and process state.

Displayable enforced states are only:

```text
ENFORCED-DIAGNOSTIC
ENFORCED-AUTHENTICATED
```

Bare `ENFORCED` is not a valid qualification label.

`ENFORCED-AUTHENTICATED` requires evidence sourced outside the controlled workload and
fresh under ADR-0015.

## Rejected alternatives

**Make `ResolvedSecurityContext` authoritative.** Rejected because repository or harness
projection forgery would then become authorization forgery.

**Create a Multi-Vault context selector.** Rejected because K0-B2 already freezes
`ContextPlanner` as the one owner of context selection.

**Store one mutable global active-vault state.** Rejected because concurrent sessions
would create cross-domain authority mixing.

**Treat repository-resident bindings as non-forgeable in GUARDED.** Rejected because
K0-B3 already demonstrates the same-user trust boundary is not separated.

**Use compatibility-by-subset for persistence in V1.** Rejected as unnecessary policy
complexity before exact-match behavior is measured.

## Consequences

- MV-02 may implement these schemas without inventing alternate authority owners.
- Canonical digest fixtures MUST be cross-platform and versioned.
- Sensitive unknowns fail closed rather than silently degrading.
- Existing K0-B authority/context contracts remain canonical and are consumed, not
  duplicated.
- A later schema change requires a versioned ADR amendment and migration semantics.
- `PRODUCTION` remains unqualified until implementation evidence, canaries and platform
  qualification exist.

## Required verification

At minimum:

```text
projection forgery grants zero data access
cross-domain handle replay denied
stale epoch handle denied
foreign caller handle denied
digest canonicalization stable across implementations/platforms
persistence assurance mismatch does not auto-load
ContextPlanner remains unique
VaultProtocol remains unique
```
