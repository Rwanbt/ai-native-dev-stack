# ADR-0019 — Multi-Forge III: release source resolution, ReleaseManifest V3, providers

- Status: accepted
- Date: 2026-09-16
- Alias: ADR-MF-03
- Materializes: Multi-Forge v1.3.2-final (frozen architecture), §18–20 and
  §33–43, §60–73, including the final addendum (`release_project_ref`,
  `AnonymousReleaseApiProvider`).
- Constrains: `ainative/lifecycle/provider.py`, `transport.py`, `updater.py`,
  `machine.py`, `ainative/lifecycle/data/`, `docs/RELEASING.md`, the release
  gates under `scripts/`, the support matrix.
- Does not modify: ADR-0009 §6 (authority commands never depend on remote
  answers); ADR-0017/0018; issue #24 (cryptographic release authority) stays
  independent — nothing here claims cryptographic provenance.

## Context

The update path knows one remote provider and one mirror format. Multi-Forge
adds GitLab.com and hardens the release contract against a class of failures
the current shape cannot express:

- a release manifest whose bytes are trusted because the source said so,
  instead of being verified against an **external** digest and size;
- an enumeration that silently truncates (endpoint pagination bounds) and
  installs the best of what it happened to see;
- duplicate publication (two packages, two assets) resolved by "first match";
- version identity drifting between candidate, manifest, runtime, artifact,
  filename and bundle protocol document;
- a SemVer `+build` suffix that makes two artifacts "the same version" while
  being different bytes;
- credentials that follow a redirect to object storage.

PR-0A (#158) already froze the transport rule — a credential is sent only to
its configured origin, computed per hop, never across an origin boundary.
This ADR freezes everything above that transport: where a source comes from,
what a provider must publish, and what the updater verifies before it trusts
a single declaration.

## Decision

### 1. One source resolver

`resolve_release_source()` is the only function that decides where a release
comes from. `update`, `update check`, `status` and `doctor` all consume it;
there is no second path and no command-specific default. Conflict validation
runs **before** precedence: two selectors that contradict each other are
refused, never ordered.

### 2. Selector rules (exact, no last-selector-wins)

```text
AINATIVE_UPDATE_PROVIDER=local + AINATIVE_UPDATE_LOCAL_DIR
    → LocalDirectoryProvider
AINATIVE_UPDATE_LOCAL_DIR without explicit provider=local
    → UPDATE_SOURCE_CONFLICT
AINATIVE_UPDATE_URL mixed with a provider/local selector
    → UPDATE_SOURCE_CONFLICT
AINATIVE_UPDATE_URL alone
    → AnonymousReleaseApiProvider (no credentials)
named provider (e.g. gitlab)
    → machine config, else built-in
nothing selected
    → machine default_provider, else built-in GitHub.com
```

### 3. Machine-scope trust configuration

Release provider configuration lives at `~/.ai-native/release-providers.json`
— machine scope, one file, reserved provider names refused when they would
shadow a built-in. **No project-local provider trust config exists**: a cloned
repository must never be able to redirect a user's updates or name its own
credential origin. The resolver reports its choice: effective source,
selection reason, authenticated yes/no, auth origin when applicable. Never a
secret value.

### 4. Endpoint configuration: trust is separated from the secret

```text
ReleaseProviderEndpointConfig:
    provider              reserved name ("github", "gitlab", "local", ...)
    api_base_url          provider API root
    auth_origin           the ONE origin allowed to receive the credential
    api_version           API dialect header where the provider requires one
    release_project_ref   where required (GitLab); numeric ID or namespace path
    credential_source     where the credential comes from (environment, ...)
```

`auth_origin` is configuration. A response can never widen it; a repository
can never set it. An endpoint without an `auth_origin` is anonymous by
construction.

### 5. Transport split (metadata / artifact), per PR-0A

- **Metadata** (release documents, file listings): same-origin redirects only;
  cross-origin is refused.
- **Artifact** (release bytes): cross-origin redirects are followed — a CDN
  hop is legitimate — always anonymously; every credential is recomputed per
  hop and never crosses an origin boundary.
- GitHub private assets are fetched through the release asset API with
  `Accept: application/octet-stream`; the browser download URL is never
  authenticated.
- GitLab object storage: an authenticated API request may redirect to the
  object store; all GitLab credentials are stripped, HTTPS is required, and
  the fetched bytes are verified against the expected digest.

### 6. Anonymous release API compatibility

`AINATIVE_UPDATE_URL` remains HTTPS, anonymous and
GitHub-Release-API-compatible. It is not a ZIP URL, not a generic mirror
index, not arbitrary JSON. If V3 integrity metadata is missing from what it
serves, the update fails closed. Its anonymity is frozen by ADR-MF-03 here and
implemented by PR-0A.

### 7. ReleaseManifest V3

```text
release manifest:  schema · protocol · version · channel ·
                   compatibility · artifacts[] · provenance
```

- The manifest is fetched and verified **before it is parsed**: its SHA-256
  and size are supplied externally (provider metadata / mirror index).
- A provider enumeration returns `EnumerationResult`. `complete=false` (bounds
  reached before exhaustion) refuses with `RELEASE_ENUMERATION_INCOMPLETE`; a
  complete, compatible channel with zero candidates refuses with
  `RELEASE_NO_CANDIDATE`. Partial results are never used silently.
- V1 compatibility mode is `exact-runtime`: a V1-era consumer applies only a
  manifest whose compatibility names the running runtime exactly.

### 8. SemVer policy for installable releases

```text
allowed:  1.2.3        1.2.3-rc.1
rejected: 1.2.3+build1      → RELEASE_BUILD_METADATA_UNSUPPORTED
```

Ordering uses an explicit release precedence key (never string order). Two
candidates with the same canonical precedence but conflicting release
identities are refused: `RELEASE_DUPLICATE_VERSION` — "first match" is not a
policy.

### 9. The trust chain, stated as a sequence

```text
provider metadata
  → manifest SHA-256 + size (external anchor)
  → download manifest
  → verify size + SHA-256
  → parse manifest
  → select the lifecycle artifact
  → download artifact
  → verify size + SHA-256
```

Trust-bearing artifact declarations are never parsed before the manifest is
verified. There is no path that skips a step "because the source is trusted".

### 10. The exact version chain

```text
candidate.version
  == manifest.version
  == compatibility.runtime_version
  == artifact.version
  == artifact filename version
  == lifecycle-protocol.json.release_version
```

Any inequality refuses with `UPDATE_VERSION_MISMATCH`. This chain already
exists for V2 (AUD-201); V3 keeps it and adds `compatibility.runtime_version`
to it. The runtime contract remains exact equality — no compatibility matrix.

### 11. Providers

- **GitHub.com** (V1 target): bounded enumeration, release asset metadata,
  manifest digest/size anchor, private assets, API version header,
  authenticated API requests, anonymous CDN redirects. GHES is not declared.
- **Local directory** (V1 target): `releases.json` must provide the manifest
  locator, its size and its SHA-256, and the local provider executes the same
  logical verification chain as a network provider. "It is on disk" is not an
  integrity argument.
- **GitLab.com** (V1 target): Releases API for discovery/version/presentation
  only; the **Generic Package Registry is the canonical distribution and
  integrity surface**. One project identity (`release_project_ref`, numeric ID
  or namespace path — never a URL) is used for Releases, packages and package
  files. Package lookup is exact (`type == generic`, canonical package name,
  selected version) and requires exactly one match; duplicate handling refuses.
  Pagination enumerates to exhaustion within configured bounds, otherwise
  `RELEASE_ENUMERATION_INCOMPLETE`. The manifest file is
  `ainative-release-v3.json`; zero matches → `RELEASE_MANIFEST_MISSING`, more
  than one → `RELEASE_MANIFEST_AMBIGUOUS`. Integrity anchors are the package
  file API's `file_sha256` and `size`; absent → `RELEASE_INTEGRITY_METADATA_MISSING`,
  malformed → `RELEASE_INTEGRITY_METADATA_INVALID`. Release Link URLs are
  presentation, never integrity roots.

### 12. Secret patterns are mandatory, not configurable-in-place

The scanner contract is `extra_secret_patterns=()`; the effective set is
`MANDATORY_SECRET_PATTERNS ∪ operator extras`. Repository configuration may
not remove, replace, disable or shadow a mandatory pattern. The minimum set
includes private key markers, the AWS/GitHub/Slack patterns already supported,
and documented GitLab token prefixes. GitLab Self-Managed qualification
carries an `access_token_prefix` tuple: a custom prefix requires an operator
extra pattern **and** a fixture proving detection, or the tuple stays
unqualified.

### 13. Qualification is declared, not assumed

- Always qualify GitLab.com if V1 declares it supported.
- GitLab Self-Managed: qualify if an environment is available; otherwise the
  tuple is `UNTESTED` and **not declared supported**. Missing Self-Managed
  infrastructure never blocks the V1 release.
- GHES: never declared in V1; a qualification checklist (version, API version,
  asset digest availability, private asset behavior, auth origin, redirect
  behavior, manifest flow, platform results) is recorded for later.
- Matrix invariant: **declared support ≤ actually qualified support**.

### 14. V3 publication gate (V2 bridge)

The first V3 publication requires `V3_BRIDGE_RELEASE=<version>`: the pipeline
verifies the bridge release exists, is published, and carries a V2 lifecycle
bundle; otherwise it blocks the release. A documented manual upgrade path
exists for pre-bridge runtimes.

### 15. Failure policy

Any uncertainty — auth origin, redirect origin, manifest digest, artifact
digest, manifest ambiguity, package ambiguity, selector conflict, enumeration
completeness — results in REFUSE UPDATE. Never warning-and-continue.

## Rejected alternatives

- **Universal Forge SDK / generic `ForgeHttpClient`.** Rejected: providers
  differ in integrity surfaces and identity semantics; one abstraction wide
  enough to cover them becomes the place where those differences are blurred.
- **Project-local provider trust config** (`.ai-native/release-providers.json`
  in a repository). Rejected: a cloned repo could redirect updates or name a
  credential origin.
- **Warning-and-continue on integrity uncertainty.** Rejected: an update that
  cannot verify itself is not an update (the #126 rule, at V3 scale).
- **Release Link URLs / browser URLs as integrity roots.** Rejected: they are
  presentation endpoints; the package file API carries the anchor.
- **"Pick the highest/inner match" on duplicates.** Rejected: duplicates are a
  publication defect; failing closed is the only deterministic outcome.
- **Allowing `+build` metadata.** Rejected: two different artifacts must not
  share an installable version identity.
- **A compatibility matrix for the runtime contract.** Rejected: strict
  equality has no silent-permission surface; no release has needed one.
- **Claiming GHES / Self-Managed support "by design similarity".** Rejected:
  declared support must not exceed qualification.

## Consequences

- PR-4 (#165) and PR-5 (#166) implement this ADR; PR-0A (#158) already
  implements its transport core; PR-0B (#157) must ship in a V2-compatible
  bridge release before any V3 publication.
- Breaking behavior changes, documented in the CHANGELOG: conflicting update
  selectors now fail closed; `AINATIVE_UPDATE_URL` is anonymous; `+build`
  metadata is unsupported for installable V3 releases; a state migrated to V2
  requires a newer CLI (ADR-0017).
- Provider diagnostics become observable (`source`, `reason`, `authenticated`,
  `auth_origin`) without exposing secrets.
- The support matrix is the honest published surface: Generic Git, GitHub.com,
  GitLab.com; GitLab Self-Managed and GHES `UNTESTED`, not supported.
