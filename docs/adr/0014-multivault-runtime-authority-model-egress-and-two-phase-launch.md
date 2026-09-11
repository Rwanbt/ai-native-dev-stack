# ADR-0014 — Runtime authority, model egress, and two-phase sensitive launch

- Status: proposed
- Date: 2026-09-11
- Alias: ADR-MV-002
- Materializes: Multi-Vault v2.5+FIX FROZEN SECURITY DESIGN and final freeze erratum.
- Constrains: future `ainative/runtime/`, `ainative/exec/`, `ainative/harness/`,
  Runtime Authority lifecycle, `ApprovedModelEgress`, provider qualification,
  two-phase launch, runtime observation, liveness and sensitive-session admission.
- Does not modify: ADR-0001 through ADR-0013; Verified Work Plane authority;
  K0-B2 ContextPlanner ownership; K0-B3 trust findings.
- Security status: design frozen; provider/harness/platform capability evidence pending
  MV-00.

## Context

Multi-Vault must safely support multiple harnesses and multiple provider classes without
pretending that AI Native intercepts model calls it does not proxy.

Earlier review exposed two distinct questions that must never be collapsed:

```text
Can the harness keep provider/model/routing fixed?
Which provider/model/routing is actually authorized?
```

A harness may be perfectly controllable while using an unapproved model. Conversely,
some harness/provider combinations can expose their effective model only from a live
process. Sensitive worktrees must not be made available merely to discover whether that
process is safe.

The current repository trust boundary is not separated. This ADR therefore specifies a
fail-closed qualification model that can produce `GUARDED` today and
`ENFORCED-*` only when stronger evidence exists.

## Decision

### 1. Runtime Authority partitioning

Run one Runtime Authority instance per `security_domain_id`.

An authority instance MUST NOT load provider credentials, vault credentials or
authorization secrets from unrelated domains.

The authority owns authoritative handle lookup and revocation state. Harness output,
repository config and natural-language input are never authority sources.

### 2. `ApprovedModelEgress`

The authoritative egress policy is:

```text
ApprovedModelEgress {
  provider_class
  provider_principal_binding
  allowed_model_ids
  allowed_model_families
  allowed_routing_classes
  allowed_endpoint_policy
  allowed_egress_class
  dynamic_routing_policy
  fallback_policy
}
```

This policy is trusted operator/domain configuration, never repository-controlled
configuration.

### 3. Provider classes

Every provider adapter declares exactly one class:

```text
cloud_api
onprem_managed
local_runtime
```

#### `cloud_api`

Relevant attestable identities may include:

```text
account/org/workspace principal
model ID/version
endpoint identity
routing class
qualified auth store/channel
```

#### `onprem_managed`

Relevant identities may include:

```text
deployment identity
tenant/project identity
endpoint identity
model deployment identity
network class
qualified auth channel
```

#### `local_runtime`

Relevant identities may include:

```text
runtime binary identity
runtime instance identity
model artifact identity/digest
local endpoint identity
network-egress policy
```

A missing cloud-style "principal" is not itself failure for local/on-prem. The relevant
security identity for the declared provider class must still be attestable.

Unknown or unattestable security-relevant identity fails sensitive qualification.

### 4. Model aliases and dynamic routing

For `CONFIDENTIAL` and `CRITICAL`, an unversioned model alias is treated as dynamic
routing unless the provider exposes an effective version/model identity that is
attestable before sensitive exposure and allowed by `ApprovedModelEgress`.

Default:

```text
unversioned alias
→ dynamic/unknown future implementation
→ DENY sensitive qualification
```

Automatic fallback, provider substitution or downstream model selection is likewise
denied unless every possible destination is explicitly covered by policy and
attestation.

### 5. Client-side attestation is not provider-backend attestation

AI Native can attest only information observable through the qualified client/provider
interface.

It MUST NOT infer from `model_id` alone guarantees about:

```text
server-side routing
physical region
data residency
retention
training use
subprocessors
opaque backend substitution
```

Such requirements require separate provider policy/contract evidence or a verifiable
provider attestation surface.

### 6. Harness capability manifest

Each harness/provider/platform adapter exposes a versioned manifest containing at least:

```text
provider_selection_control: verified | partial | none
model_selection_control: verified | partial | none
endpoint_routing_control: verified | partial | none

provider_principal_observation:
  event | poll(max_interval) | per_operation | none

model_identity_observation:
  event | poll(max_interval) | per_operation | none

endpoint_routing_observation:
  event | poll(max_interval) | per_operation | none

auth_store_observation:
  event | poll(max_interval) | per_operation | none

two_phase_attestation:
  static | probe | none

session_containment:
  verified | partial | none
```

Evidence is keyed by:

```text
harness version
provider
platform
adapter version
probe version
```

A new untested harness version is `UNKNOWN`, not inherited-compatible.

### 7. Classification defaults

For `CONFIDENTIAL` and `CRITICAL`:

```text
provider selection       VERIFIED
model selection          VERIFIED
endpoint routing         VERIFIED
PARTIAL                   DENY by default
required observation     bounded/event/per-operation
session containment       VERIFIED
```

A sensitive `PARTIAL` exception may only come from trusted Operator Authority Store
policy and must name the exact residual limitation. Repository policy cannot grant the
exception.

### 8. Two-phase launch

When all egress properties are statically attestable, the adapter may use static
attestation.

When a live process is needed, use two phases.

#### Phase A — neutral attestation

The probe process runs with:

```text
neutral cwd
no sensitive worktree
no RuntimeContextHandle
no sensitive persistent memory
no vault access
no sensitive MCP capability
positive child environment constructed from {}
```

Under `GUARDED`, this is a policy gate, not a same-user filesystem sandbox. A hostile
same-user process remains outside the GUARDED threat model.

#### Phase B — governed session

Sensitive worktree/context access and the RuntimeContextHandle become available only
after successful qualification and carried-state revalidation.

### 9. `CarriedStateContract`

The Phase A → Phase B binding contains:

```text
harness_binary_identity
harness_version
config_root_digest
provider_principal
effective_model_id
routing_class
endpoint_policy_digest
plugin_inventory_digest
adapter_version
probe_version
```

Before releasing sensitive context in Phase B, every security-relevant property that can
be re-measured MUST be re-measured.

If a required property cannot be re-measured or safely bound across the transition:

```text
probe_attestation_incomplete
→ capability NONE
→ CONFIDENTIAL/CRITICAL DENY
```

There is no "best effort" sensitive promotion.

### 10. Runtime assumption observation

Every assumption whose invalidation revokes a capability declares one of:

```text
per_operation
event
poll(max_interval)
external_verifier + freshness mode
none
```

Required sensitive assumption + `none` is denial.

Minimum observed assumptions include:

```text
provider principal
effective model
endpoint/routing
provider auth store
semantic config
plugin inventory
binding/approval validity
vault root identity
execution boundary state
launcher liveness
Runtime Authority liveness
```

### 11. Drift semantics

AI Native does not promise to recall a native provider request already in flight.

When relevant drift is observed:

```text
revoke RuntimeContextHandle
revoke governed capabilities
terminate the contained governed workload
require a new qualified launch
```

The residual window for polling is:

```text
max_observation_interval + termination_latency
```

and is recorded in qualification evidence and session audit metadata.

### 12. Mutual liveness

Launcher and Runtime Authority monitor each other with bounded liveness.

```text
launcher_liveness:
  heartbeat(max_interval)

authority_liveness:
  heartbeat(max_interval)
```

Loss of launcher:

```text
authority revokes handle
containment closes
governed workload terminates
audit LAUNCHER_LOST
```

Loss of Runtime Authority:

```text
launcher terminates governed workload
```

The liveness residual window is:

```text
max(launcher_detection_interval, authority_detection_interval)
+ termination_latency
```

A sensitive session with no demonstrable bound is denied.

### 13. `session_containment = VERIFIED`

`VERIFIED` requires both:

```text
escape resistance
+
supervisor-loss fail-dead semantics
```

Escape resistance means descendants carrying sensitive workload state cannot voluntarily
leave the qualified containment primitive.

Fail-dead means the workload cannot remain alive after all designated security
supervisors disappear.

A polling-only watchdog does not by itself qualify this property. The containment must be
held so that loss of all authorized holders closes/kills the workload, or an independent
external containment owner must itself be a separately qualified authority whose own
lifecycle does not reintroduce the same unsolved dependency.

Platform examples:

- Windows candidate: Job Object, breakaway disabled,
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, with handle ownership proven by spike.
- Linux candidate: cgroup v2/systemd scope or another empirically proven mechanism.
- POSIX process group/`killpg` alone: at most `PARTIAL`.
- macOS: `UNKNOWN/PARTIAL` until MV-00 proves an adequate primitive.

Until proven otherwise, a platform without `VERIFIED` containment cannot run
`CONFIDENTIAL/CRITICAL`.

### 14. ENFORCED boundary freshness

`ENFORCED-AUTHENTICATED` requires boundary evidence sourced outside the controlled
workload.

Each measured boundary property has temporal semantics:

```text
event
poll(max_interval)
per_operation
```

Evidence that exceeds its freshness window invalidates the current
`ExecutionBoundaryDigest`, revokes the enforced qualification and applies the relevant
termination policy.

`ENFORCED-DIAGNOSTIC` must never be displayed as authenticated enforcement.

## Rejected alternatives

**Proxy every model call through AI Native.** Rejected as a mandatory architecture
because the supported harnesses may own native provider calls. Qualification must remain
honest about where AI Native is and is not in the path.

**Treat `model_selection_control=verified` as model authorization.** Rejected because
control and authorization are distinct.

**Allow aliases because the provider is trusted.** Rejected because an alias can change
the effective model without a policy change.

**Launch directly in the sensitive worktree, then inspect the session.** Rejected because
qualification would occur after exposure.

**Use process groups as verified containment on POSIX.** Rejected because detached
descendants can escape.

**Use an unbounded heartbeat.** Rejected because "eventual termination" is not a
measurable security property.

## Consequences

- MV-00 must discover which harness/provider/platform tuples actually qualify.
- It is valid for the result to be "no current harness qualifies for sensitive use".
  The architecture must not be weakened merely to make a harness pass.
- `CONFIDENTIAL/CRITICAL` support may initially be Windows-only if that is the only
  platform where containment and pre-exposure attestation are demonstrated.
- Provider aliases may substantially reduce the eligible harness/provider set.
- ENFORCED claims remain unavailable until external evidence exists.
- MV-07/MV-08 implementation must follow these contracts rather than introduce new
  egress or containment policy.

## Required MV-00 evidence

At minimum:

```text
effective provider identity
effective model identity
model alias behavior
fallback/dynamic routing
pre-call vs post-call model identity
Phase A → B carried-state continuity
provider auth-store drift
project autoload suppression
launcher loss
Runtime Authority loss
simultaneous supervisor loss
detached child / setsid / double fork
Windows Job breakaway
platform-specific containment result
```
