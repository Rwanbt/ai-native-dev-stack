# ADR-0015 — Scoped vault access, IPC identity, subprocess hygiene, and ENFORCED qualification

- Status: proposed
- Date: 2026-09-11
- Alias: ADR-MV-003
- Materializes: Multi-Vault v2.5+FIX FROZEN SECURITY DESIGN and final freeze erratum.
- Constrains: future `ainative/obsidian/`, `ainative/mcp/`, `ainative/rest/`,
  security-critical subprocess spawning, vault-filesystem freshness, semantic/graph
  admission, canary qualification and ENFORCED component placement.
- Does not modify: ADR-0001 through ADR-0014; VaultProtocol v4 ownership;
  ContextPlanner ownership; existing Verified Work Plane authority.
- Security status: design frozen; REST, plugin and platform evidence pending MV-00/MV-01.

## Context

Multi-Vault adds multiple sensitive data domains to a stack that already uses Obsidian,
Local REST, MCP-style integration, semantic retrieval and harness-specific execution.

The risk is not only "wrong path". A stale environment variable, foreign caller, reused
endpoint, background semantic plugin, swapped vault root or privileged subprocess
inheriting shell state can cross a domain even when the high-level workspace selection
looks correct.

The frozen design therefore requires:

- thin, session-bound adapters rather than a global vault authority endpoint;
- positive environment construction for every security-critical child;
- physical path/root revalidation;
- explicit semantic/graph result confinement;
- fail-closed canary qualification;
- honest distinction between GUARDED checks and ENFORCED authenticated isolation.

## Decision

### 1. Thin MCP Adapter lifecycle

A thin MCP adapter instance is bound to exactly:

```text
one launcher
one security_domain_id
one RuntimeContextHandle lineage
one ephemeral endpoint
```

It starts with the governed launcher and dies with it. Endpoint identifiers are never
reused across sessions.

Every request requires:

```text
session capability
+
authenticated caller identity
```

Missing, expired, foreign or replayed capability:

```text
DENY
+
audit metadata
```

The adapter is a transport/projection layer. It does not own context selection or vault
authorization.

### 2. Runtime Authority IPC

Generic loopback HTTP MUST NOT be used as the authority authentication primitive.

Preferred authenticated local IPC:

```text
Windows named pipe + ACL/peer identity
Unix-domain socket + peer credentials
inherited descriptor where applicable
```

In GUARDED, caller binding also uses launcher lineage and process start identity where
reliable.

In ENFORCED, the IPC endpoint itself must be outside or appropriately protected from the
controlled workload.

### 3. Positive environment for all security-critical subprocesses

The empty-environment rule applies to every privileged/security-critical child, not just
the harness.

Examples include:

```text
Git transfer process
SSH transport
credential helper
scanner
boundary probe
thin-MCP helper subprocess
REST helper
Git-LFS detector
trusted executable probe
```

Construction:

```text
{}
+ required and sanitized OS variables
+ explicitly approved transport variables
+ explicitly qualified credential channel
```

"Required OS variables" means a per-platform allowlist with validated/sanitized values.
It MUST NOT mean copying `PATH`, temp paths or other parent values without qualification.

Variables absent unless explicitly allowed include:

```text
GIT_CONFIG_COUNT
GIT_CONFIG_KEY_*
GIT_CONFIG_VALUE_*
GIT_ASKPASS
SSH_ASKPASS
GIT_SSH
GIT_SSH_COMMAND
HTTP_PROXY
HTTPS_PROXY
NODE_OPTIONS
PYTHONPATH
unknown future parent variables
```

Validation and real execution of a privileged operation MUST use the same effective
environment.

### 4. Trusted executable resolution

Security-critical executables are resolved outside repository/vault authority.

Repository content must not be able to shadow:

```text
git
ssh
credential helper
scanner
runtime helper
boundary probe
```

Executable identity used by validation must match the executable used by the actual
operation.

### 5. Vault filesystem freshness

The authoritative runtime snapshot records at least:

```text
canonical vault root
filesystem object/file identity where available
volume/device identity
logical vault ID
checkout identity
```

Before each privileged filesystem operation, implementations either:

```text
revalidate current root identity
```

or use an OS primitive that binds access to a stable directory handle.

Mid-session symlink, junction, mount or equivalent retargeting causes denial.

### 6. REST/local-instance correlation

The REST adapter must never infer "same vault" from a configured URL alone.

MV-00 determines which identity signals are actually observable. Qualification must bind
a REST endpoint to the intended local Obsidian/vault instance using evidence adequate for
the active profile.

Unknown endpoint/vault correlation fails sensitive qualification.

Redirects, TLS/CA behavior, hidden-file access, multi-instance behavior and credential
handoff are empirical spike questions, not assumed capabilities.

### 7. Semantic/graph admission

Smart Connections or any semantic/graph provider must pass admission before a sensitive
governed session.

For `CONFIDENTIAL/CRITICAL` require:

```text
known supported plugin/provider version
compliant semantic egress config
runtime observation mechanism
```

Unknown version:

```text
PERSONAL       warning/opt-in
TEAM           trusted policy
CONFIDENTIAL   DENY
CRITICAL       DENY
```

### 8. Semantic runtime drift

Security-relevant semantic configuration is represented by `SemanticEgressDigest`
(ADR-0013).

If it changes to a forbidden/unqualified state:

```text
revoke entire governed session
```

not merely the semantic capability.

Temporary read errors are not silently interpreted as "safe". The adapter must
distinguish at minimum:

```text
observed changed configuration
configuration unreadable
observer unavailable
```

Required sensitive observer unavailable/unreadable beyond its bounded policy fails
closed.

### 9. Semantic and graph result confinement

Every result path is:

```text
canonicalized
symlink/junction resolved
checked against AllowedContextEnvelope
checked against project_security_id
checked against VaultProtocol confinement
```

Cross-project/domain results are denied unless the authoritative envelope explicitly
includes a shared root.

### 10. VaultProtocol ownership

VaultProtocol v4 remains the single owner of vault structure and write confinement.

Multi-Vault adapters must call/consume that contract. They MUST NOT reimplement vault
path rules in a second subsystem.

### 11. Canary scanner

Canary scanner exit contract:

```text
0 = complete and clean
1 = leak found
2 = incomplete/error
```

Security qualification:

```text
1 = FAIL
2 = FAIL
```

Every `2` includes a structured reason, for example:

```text
INFRASTRUCTURE_UNAVAILABLE
PERMISSION_DENIED
STORE_LOCATION_UNKNOWN
ADAPTER_SURFACE_UNKNOWN
TIMEOUT
READ_ERROR
ENUMERATION_FAILURE
POSSIBLE_TAMPERING
```

There is no "unsafe skip" that produces a green sensitive/production qualification.

A developer bypass may exist only if it explicitly downgrades the session to a
non-qualified mode.

Under GUARDED, canaries detect accidental/operational disclosure and stale surfaces; they
are not an anti-forgery boundary against a hostile same-user process.

### 12. Managed canary surfaces

The scanner's managed inventory includes, where applicable:

```text
vaults
AllowedContextEnvelope outputs
ContextPlanner assembled outputs
semantic/graph retrieval outputs
thin MCP outputs
harness persistent stores
provider auth stores declared by adapters
transcripts
AI Native logs
runtime temp state
Git index
candidate Git objects
reachable Git history baseline
declared remote/network surfaces
```

A surface is `NOT_APPLICABLE` only when the exact adapter version/platform probe proves
it absent. New/unprobed versions are `UNKNOWN/INCOMPLETE`, never implicitly safe.

### 13. ENFORCED component placement

For `ENFORCED-*`, the controlled harness boundary contains only the controlled workload
and qualified contained descendants.

The following remain outside the controlled boundary:

```text
Runtime Authority
Operator Authority Store
raw vault
Obsidian credential-bearing state
raw REST service access
authority side of thin MCP adapter
Git security/transfer service
authenticated boundary verifier
foreign-domain credentials
```

A domain-approved provider credential may enter only through an explicitly qualified
provider-auth channel.

### 14. ENFORCED evidence freshness

`ENFORCED-AUTHENTICATED` requires external evidence for each claimed boundary property.

Each property defines one of:

```text
event
poll(max_interval)
per_operation
```

Stale evidence invalidates `ExecutionBoundaryDigest`, revokes
`ENFORCED-AUTHENTICATED` and invokes the runtime revocation/termination contract in
ADR-0014.

`ENFORCED-DIAGNOSTIC` may display locally observed evidence but may not claim authenticated
enforcement.

### 15. Platform scope

A platform without proven sensitive containment or required IPC/evidence primitives is
`UNKNOWN/PARTIAL`.

In V1 this means, unless MV-00 proves otherwise:

```text
Windows: candidate for CONFIDENTIAL/CRITICAL qualification
Linux: candidate pending cgroup/fail-dead evidence
macOS: PERSONAL/TEAM only
```

This is a qualification result, not an architecture failure.

## Rejected alternatives

**Expose one long-lived global MCP/REST adapter for all vaults.** Rejected because it
creates shared authority and credential state across domains.

**Use loopback reachability as caller authentication.** Rejected because same-user
processes can reach the port.

**Copy the parent environment then delete known dangerous variables.** Rejected because
unknown/future variables and command-scope injection remain possible.

**Trust semantic provider output paths.** Rejected because retrieval providers are not
path authorities.

**Treat canary infrastructure failure as success.** Rejected because incomplete coverage
cannot support a sensitive qualification.

**Call local diagnostic evidence `ENFORCED`.** Rejected because current repository
evidence does not establish a separated production trust boundary.

## Consequences

- MV-00 must empirically qualify REST, plugin egress and platform IPC/containment.
- MV-01 canary baseline is a security gate and may legitimately block sensitive
  qualification while infrastructure is incomplete.
- Thin adapters remain small because authority stays in Runtime Authority and
  ContextPlanner/VaultProtocol remain canonical owners.
- Security-critical child spawning must use one shared positive-environment primitive
  rather than per-call deny lists.
- Production trust remains unavailable until external boundary evidence exists.

## Required verification

At minimum:

```text
foreign thin-MCP caller denied
expired session capability denied
endpoint not reused across sessions
unknown parent environment absent
security-critical OS env values sanitized
trusted executable cannot be shadowed by repo
vault root swap denied
cross-project semantic result denied
semantic config drift revokes full session
unknown plugin version denied for sensitive profiles
canary exit 2 fails qualification with reason
unprobed adapter version is incomplete
stale ENFORCED evidence revokes qualification
```
