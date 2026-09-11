# ADR-0016 — Multi-Vault Git and sync isolation

- Status: proposed
- Date: 2026-09-11
- Alias: ADR-MV-004
- Materializes: Multi-Vault v2.5+FIX FROZEN SECURITY DESIGN and final freeze erratum.
- Constrains: future `ainative/git/`, `ainative/sync/`, governed Git hooks,
  remote qualification, transport policy, fetch evidence, push intent,
  candidate-object scanning, LFS behavior and sensitive sync writer ownership.
- Does not modify: ADR-0001 through ADR-0015; Git itself; VaultProtocol ownership;
  K0-B3 canonical-mutation authority.
- Security status: design frozen; Git/platform behavior pending MV-00.

## Context

A sensitive vault can leak or ingest data even when the configured Git URL appears
correct.

Git behavior can be changed by:

```text
remote identities
URL rewrites
SSH commands
proxies
credential helpers
config includes
command-scope environment config
submodule recursion
partial/promisor remotes
lazy object fetch
Git LFS
hooks
multiple refs
force/deletion behavior
```

A pre-push hook alone cannot hold a lock through the actual transfer, and Git has no
simple universal pre-fetch hook. Under same-user GUARDED, arbitrary manual filesystem or
Git mutation cannot honestly be given non-forgeable provenance.

The design therefore guarantees strongly governed transfer paths, keeps local-state
admission diagnostics honest about their threat model, and disables secondary sensitive
network channels that would otherwise need their own remote-governance system.

## Decision

### 1. `ApprovedGitRemote`

Every governed network operation uses a trusted remote declaration:

```text
ApprovedGitRemote {
  canonical_fetch_url
  canonical_push_url
  provider_type
  stable_repository_id
  required_owner_org
  required_visibility_for_push
  allowed_refs
  fetch_policy
  push_policy
}
```

For `CONFIDENTIAL/CRITICAL`:

```text
require_stable_repository_id = true
```

If the hosting provider cannot establish the required stable repository identity,
sensitive qualification is denied.

Remote URL equality alone is not repository identity.

### 2. Fetch and push remote checks

Before governed fetch/pull/update or push as required by policy, validate:

```text
stable repository ID
required owner/org
canonical effective URL
approved identity
required visibility for push
allowed refs
```

Client-side visibility/identity verification is a freshness guarantee, not an atomic
guarantee against a concurrent remote administrator change. Stronger guarantees require
server-side policy.

### 3. `GitTransportPolicy`

Every governed Git network operation also binds:

```text
GitTransportPolicy {
  protocol
  transport_executable_identity
  proxy_policy
  credential_helper_policy
  ssh_peer_policy
  tls_peer_policy
  protocol_allowlist
  effective_transport_config_digest
}
```

Validation covers the actual effective transport, not merely intended configuration.

### 4. Security-critical Git environment

ADR-0015's positive-environment rule applies to Git validation and transfer.

The validator and actual Git subprocess MUST use the same effective environment.

The subprocess starts from `{}` plus explicit approved values. Parent shell state such as
the following is absent unless explicitly qualified:

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
GIT_CONFIG_GLOBAL
GIT_CONFIG_SYSTEM
```

This prevents a validation/transfer TOCTOU where Git sees command-scope configuration the
validator did not.

### 5. Effective configuration surfaces

Sensitive transport qualification neutralizes or validates at minimum:

```text
core.sshCommand
GIT_SSH
GIT_SSH_COMMAND
core.gitProxy
HTTP_PROXY
HTTPS_PROXY

credential.helper
credential.useHttpPath
GIT_ASKPASS
SSH_ASKPASS

url.*.insteadOf
url.*.pushInsteadOf

remote.*.url
remote.*.pushurl
remote.*.fetch

include.path
includeIf.*

GIT_CONFIG_GLOBAL
GIT_CONFIG_SYSTEM
GIT_CONFIG_NOSYSTEM
GIT_CONFIG_COUNT
GIT_CONFIG_KEY_*
GIT_CONFIG_VALUE_*

http.proxy
http.sslVerify
http.sslCAInfo
http.sslCert
http.sslKey

unexpected custom protocol helpers
unexpected transport executable
unexpected SSH/CA policy
```

Multi-valued configuration is reset and rebuilt from an allowlist where necessary, not
merely appended with additional `git -c` entries.

### 6. No-network policy resolution

Resolving the effective destination/transport configuration MUST make zero external
network connection before the operation has been authorized.

MV-00 verifies that the implementation technique used for config/transport resolution
satisfies this property.

### 7. `FetchTransferEvidence`

Every governed fetch-like transfer produces:

```text
FetchTransferEvidence {
  ApprovedGitRemote
  GitTransportPolicy
  requested_refs
  effective_transport_config_digest
  verified_remote_identity
  verified_at
}
```

Remote identity and transport evidence are valid before the first network connection.

### 8. Direct/manual fetch under GUARDED

GUARDED guarantees provenance for governed fetches.

It does NOT claim cryptographic provenance for arbitrary same-user local Git/object
store/worktree mutations such as:

```text
git fetch <arbitrary-url>
git checkout FETCH_HEAD -- file
manual copy
git apply
git reset
manual object insertion
```

Such actions are equivalent to arbitrary local edits under the GUARDED threat model.

ENFORCED may claim stronger prevention only when alternate Git/filesystem/network paths
are technically inaccessible.

### 9. Local repository admission diagnostics

The system maintains a versioned locally recorded state for stale/accidental-change
detection:

```text
last_verified_repository_state {
  schema_version
  approved_remotes
  refs { ref_name, oid }
  index_tree_digest
  worktree_security_digest
  last_fetch_evidence_digest
  verified_at
}
```

Under GUARDED this state is advisory/defense-in-depth and is not a hostile same-user
anti-forgery root.

Admission checks compare, as policy requires:

```text
approved remote set
local refs
remote-tracking refs
tags
HEAD
index tree
selected security-relevant worktree state
```

Unexpected state may produce:

```text
AINATIVE_GIT_LOCAL_STATE_UNVERIFIED
```

and refuse a governed sensitive launch, while still making no stronger provenance claim.

### 10. `worktree_security_digest`

This digest exists for accidental/stale-state detection and admission latency must remain
bounded.

ADR schema/implementation may compose:

```text
HEAD/local refs
index tree
security-relevant tracked paths
relevant Git config
repository metadata used by policy
optional targeted/sampled content evidence
```

It is not a full same-user provenance proof.

### 11. Unapproved remotes

A sensitive governed checkout declares only approved remotes.

An additional remote produces:

```text
AINATIVE_GIT_UNAPPROVED_REMOTE_PRESENT
```

at governed admission/doctor checks.

`remote.*.url`, `remote.*.pushurl` and `remote.*.fetch` are inspected.

This catches common accidental `upstream`/wrong-remote use without claiming protection
against a hostile same-user editor.

### 12. `reference-transaction`

MV-00 tests whether Git's `reference-transaction` hook is reliable for supported
platform/version combinations.

If proven, it may be used as an additional guard rail.

No core security guarantee depends solely on this hook.

### 13. Sensitive V1 secondary Git network policy

For `CONFIDENTIAL/CRITICAL` V1:

```text
fetch recursion into submodules = DENY
push recursion into submodules  = DENY
partial clone                   = DENY
promisor remote                 = DENY
lazy missing-object fetch       = DENY
Git LFS network access          = DENY
```

Governed Git forces or validates:

```text
fetch.recurseSubmodules=false
submodule.recurse=false
push.recurseSubmodules=no
```

A `.gitmodules` file is not by itself a denial. Any operation requiring submodule network
access is denied until a future ADR defines explicit secondary-remote governance.

Detect at least:

```text
.gitmodules
submodule.*.url
extensions.partialClone
remote.*.promisor
remote.*.partialCloneFilter
```

### 14. Git LFS

For sensitive V1, no Git-LFS network activity is permitted.

Denied when network would be required:

```text
LFS hydration/download
LFS upload
LFS batch API
LFS smudge/process network access
LFS pre-push upload
custom LFS endpoint
```

Detect and neutralize at minimum:

```text
.lfsconfig
lfs.url
lfs.pushurl
filter.lfs.*
GIT_LFS_*
LFS smudge/process/pre-push integration
```

A pointer-only operation may proceed only when zero LFS network is demonstrated and all
other Git policy checks pass.

Full LFS remote governance is future work and requires an ADR amendment rather than an
implicit extension of `ApprovedGitRemote`.

### 15. Candidate object scanning

Before a governed sensitive push, construct the actual candidate object set from the
actual ref transaction.

Security scanning covers the objects that the proposed transfer would make newly
reachable, according to the implementation contract.

LFS data is not considered safely handled merely because the Git pointer is scanned.
Sensitive V1 therefore keeps LFS network denied.

### 16. `PushIntent`

The authoritative push transfer intent contains:

```text
PushIntent {
  source_oid
  expected_remote_base_oid
  target_ref
  exact_refspec
  ApprovedGitRemote
  GitTransportPolicy
  candidate_object_set_digest
  scan_result_digest
  expected_git_identity
}
```

Its canonical digest is defined in ADR-0013.

Every stdin ref line supplied to `pre-push` is processed. One invalid ref rejects the
whole governed push.

### 17. Sensitive push executor

For `CONFIDENTIAL/CRITICAL`, the governed/default push path is executed only by the AI
Native Git security/sync engine.

The engine:

```text
constructs PushIntent
scans candidate objects
validates identity
validates destination
validates transport
acquires push lock
revalidates
authorizes hook
executes transfer
holds lock through transfer completion
```

A direct ordinary sensitive push hits the guard hook and receives:

```text
AINATIVE_DIRECT_PUSH_DENIED
```

with guidance to use the governed sync/push command.

### 18. `GovernedPushCapability`

The guard hook distinguishes an engine push from an ordinary push using a one-time
capability issued by Runtime Authority, never a forgeable environment marker.

```text
GovernedPushCapability {
  nonce
  security_domain_id
  checkout_identity
  PushIntentDigest
  source_oid
  exact_refspec
  expires_at
  single_use
}
```

The hook verifies through authenticated local IPC:

```text
nonce valid
correct checkout
correct domain
not expired
not consumed
stdin refs exactly match PushIntent
```

Authorization consumes the capability transactionally.

Replay, expiry or ref mismatch is denied.

### 19. GUARDED push honesty

Under same-user GUARDED:

```text
git push --no-verify
hook replacement
manual Git invocation outside governed paths
```

cannot be physically prevented.

Therefore the guarantee is:

```text
every governed/default sensitive push path uses the AI Native transfer engine
```

not:

```text
same-user can never perform an unmediated push
```

ENFORCED may technically prevent unmediated network/Git access when its boundary owns
the relevant paths.

### 20. Push lock and worktrees

Git internal paths are resolved using Git:

```text
git rev-parse --git-dir
git rev-parse --git-common-dir
git rev-parse --git-path ...
```

The implementation does not assume `.git` is a directory.

For governed sensitive push, the lock is acquired before final revalidation and held
through real transfer completion.

Multi-checkout races remain safe through:

```text
expected_remote_base_oid
fresh remote revalidation
non-fast-forward policy
```

rather than an unnecessary global machine lock.

### 21. Force and deletion defaults

Sensitive default:

```text
force push             DENY
force-with-lease       DENY
non-fast-forward       DENY
remote ref deletion    DENY
```

Any exception requires trusted policy plus explicit interactive approval.

### 22. Sensitive sync writer

Sensitive V1:

```text
sync_driver = ainative | none
```

The AI Native validation/transfer engine itself is the writer; it is not a wrapper around
an ungoverned writer.

An active `obsidian-git` writer causes sensitive qualification denial until MV-00 proves
a safe governed behavior.

The exact "active" detection contract is implemented conservatively: if a concurrent
plugin writer capable of network sync cannot be excluded, sensitive qualification is
denied.

## Rejected alternatives

**Trust the configured Git URL only.** Rejected because URL rewrites, credentials,
proxies and same-URL repository recreation bypass that model.

**Use `pre-push` as the complete sensitive transfer engine.** Rejected because the hook
ends before Git's transfer and cannot hold the governing lock through completion.

**Permit secondary remotes in V1 and recursively approve them on demand.** Rejected
because it introduces a new multi-remote authority system before evidence demonstrates
the need.

**Allow Git LFS when a content scanner exists.** Rejected because content safety and
network-destination authorization are separate.

**Claim provenance for arbitrary manual local Git state in GUARDED.** Rejected because a
same-user actor can modify the worktree directly without Git.

**Copy the shell environment into the privileged Git process.** Rejected because command
scope Git config and future environment variables bypass static deny lists.

## Consequences

- Sensitive V1 intentionally sacrifices submodule/promisor/LFS network convenience for a
  small, auditable transfer surface.
- MV-00 must empirically test config precedence, transport discovery,
  `reference-transaction`, LFS behavior and secondary network channels.
- Direct Git commands remain possible under same-user GUARDED but are not represented as
  security-enforced paths.
- Full LFS/submodule governance, if later required, needs explicit ADR amendments.
- MV-17/18/19 implementation must keep validation evidence bound to the actual transfer
  environment and refs.

## Required verification

At minimum:

```text
remote recreated at same URL is rejected where stable ID is required
unapproved remote present is detected
fetch transport override denied
push transport override denied
GIT_CONFIG_COUNT injection denied
GIT_CONFIG_KEY/VALUE injection denied
GIT_ASKPASS unapproved denied
validation and transfer use same environment
submodule fetch recursion denied
submodule push recursion denied
partial/promisor remote denied
Git-LFS custom endpoint denied
Git-LFS smudge/pre-push network denied
pointer-only zero-network LFS operation tested
multi-ref pre-push rejects one-invalid-ref transaction
force/delete denied by default
governed push nonce nominal/expired/replay/wrong-ref tested
push lock covers transfer
fresh checkout without required hooks is not governed
```
