# ADR-0018 — Multi-Forge II: provider-neutral workflow, work authority, and claims

- Status: accepted
- Date: 2026-09-16
- Alias: ADR-MF-02
- Materializes: Multi-Forge v1.3.2-final (frozen architecture), §17 and
  §45–54.
- Constrains: `docs/FORGE-WORKFLOW.md`, `docs/GITHUB-WORKFLOW.md`,
  `docs/GITLAB-WORKFLOW.md`, `templates/AGENTS.md`, `ainative/forge.py`,
  `ainative claim-attempt`, `skills/issue-to-implementation/`.
- Does not modify: ADR-0017 (feature/state model); the repository's own
  GitHub-based policy for its own maintenance; the Verified authority
  architecture; issue #33 (stale-claim lifecycle) and #120 (managed Git guard)
  remain independent and unchanged.

## Context

The workflow policy is GitHub-shaped in its vocabulary and its mechanics:
`docs/GITHUB-WORKFLOW.md` says "Issue", "PR", "assignment"; the claim
procedure resolves against GitHub-shaped records; the distributed
`AGENTS.md` inherits that vocabulary into every project. Multi-Forge supports
Generic Git, GitHub.com and GitLab.com, and GitLab says "WorkItem" and
"ChangeRequest" — not Issue and PR.

Two failure modes must not be traded for each other:

1. **Neutrality without authority.** A generic workflow that cannot say *which*
   remote is authoritative silently picks one — origin, upstream, the first
   remote — and then mutates the wrong backlog.
2. **Convenience without durability.** A claim is a remote mutation. If the
   local record of an attempted claim is lost — no journal, or a journal
   written after the POST — a crash leaves an agent unable to tell "my claim
   landed" from "my claim never left", and the only safe-looking remedy
   (POST again) is how duplicate claims are created.

The architecture review for the existing policy is closed (see
`docs/GITHUB-WORKFLOW.md`); this ADR does not reopen its decisions, it
generalizes their vocabulary and adds the claim-durability layer.

## Decision

### 1. Terminology: Work Authority, WorkItem, ChangeRequest, WorkAuthorityRef

- **Work Authority** — the remote whose work records are authoritative for a
  project: one provider (github, gitlab, or none for Generic Git) plus a
  project identity on that provider.
- **WorkItem** — the unit of work on that authority (GitHub Issue, GitLab
  WorkItem).
- **ChangeRequest** — the reviewable change (GitHub PR, GitLab MR).
- **WorkAuthorityRef** — the canonical reference: `provider` + stable project
  identity. Not a URL, not a remote name, not a hostname guess.

The distributed policy documents (`docs/FORGE-WORKFLOW.md`) speak only this
vocabulary. `docs/GITHUB-WORKFLOW.md` and `docs/GITLAB-WORKFLOW.md` become
explicit mappings onto it: they name the provider's record kinds, its claim
signals (assignment, comment/note, event identifiers) and its error surfaces.
The repository's own root `AGENTS.md` may remain GitHub-specific: it governs
this repository's own workflow, not the distributed model.

### 2. Ownership: remote facts belong to the skill/harness; the resolver is pure

Reading and mutating remote state is done by the harness or skill that holds
the provider's tooling and credentials. `ainative/forge.py` adds exactly one
thing: a **pure local resolver**:

```text
resolve_observed_work_authority(...) -> WorkAuthorityRef | refusal
```

It has no network, no credential lookup, no writes, no provider API calls and
no Multi-Vault push authorization. It consumes facts observed elsewhere
(remote names/URLs, explicit harness declarations, explicit WorkItem or
ChangeRequest references) and returns an authority or a refusal.

Resolution priority, in order:

1. an explicit WorkItem/ChangeRequest repository reference;
2. an explicit harness-declared authority;
3. **exactly one** compatible observed candidate;
4. otherwise a refusal: `WORK_AUTHORITY_UNAVAILABLE`,
   `WORK_AUTHORITY_AMBIGUOUS`, `WORK_AUTHORITY_MISMATCH`.

Observed candidates are diagnostic only: an `origin` and an `upstream` that
disagree (a fork) resolve to `AMBIGUOUS`, never to a preference. A remote URL
is evidence, never authority; self-hosted providers are not inferred from a
hostname (PR-3 renders `unknown` rather than guessing).

### 3. Claim identity is canonical, not local

A claim is identified by provider-stable facts, never by local formatting:

```text
principal  <provider>:principal:<stable-provider-id>
event      <provider>:<event-kind>:<stable-event-id>
```

V1 event kinds: `comment`, `note`, `assignment`. A "claim event" is the record
of a claim signal; a later assignment never rewrites an earlier comment. All
timestamps are normalized to UTC at observation. Winner ordering is a total
order: `(created_at_utc, canonical_event_identifier)` ascending. An
unorderable pair is `CLAIM_CONFLICT` and every claimant stops — the existing
ADR-0009-era rule, restated in provider-neutral terms.

### 4. ClaimAttempt journal: durable, local, non-authoritative

Every claim attempt is journaled before the remote POST:

```text
.ai-native/state/claim-attempts/
```

The directory is covered by the existing managed `.ai-native/state/` ignore
rule. A journal entry is **local** (never synced), **durable** (written
atomically, fsynced by the existing atomic-write helpers), **non-authoritative**
(it does not decide anything by itself) and **non-Verified** (it is never
evidence for a convergence verdict).

### 5. The claim mutation algorithm

```text
READ  the WorkItem
READ  linked active ChangeRequests (a linked PR/MR is a claim-level conflict)
GENERATE attempt_id
WRITE the PENDING attempt atomically
      on local write failure → CLAIM_JOURNAL_UNAVAILABLE, STOP (no POST)
POST  exactly one claim signal, carrying a deterministic attempt marker
READ  the remote state again
SEARCH for the exact attempt marker
ARBITRATE against every other canonical claim event
persist the outcome in the journal
```

Journal-before-POST is the invariant that makes crash recovery possible: an
attempt that crashed after the POST is found by its marker on the remote; an
attempt that crashed before it is provably local-only.

### 6. Outcomes, failure policy, and recovery

Outcomes: `CONFIRMED`, `LOST`, `CONFLICT`, `UNCERTAIN`, `ABANDONED`.

- An unknown POST result is `UNCERTAIN`. It is **never** automatically
  re-POSTed: the marker search is the only way to resolve it.
- A corrupt or unreadable journal fails closed (`CLAIM_JOURNAL_UNAVAILABLE` /
  `UNCERTAIN`), never "assume it did not happen".
- There are no leases, no heartbeats, no age-based expiration and no
  timestamp-inferred abandonment.
- `ABANDONED` is an explicit operator transition. Only after it may a new
  attempt be created; abandonment is local only (no remote mutation) and the
  record is retained.
- Recovery CLI: `ainative claim-attempt list`, `inspect <id>`,
  `abandon <id> --confirm`.

A normal lifecycle update must leave pending ClaimAttempt files byte-identical
(the journal belongs to the project's state area but is not lifecycle-owned).

### 7. No remote work API clients

Neither this layer nor any neutral module calls a provider work API. There is
no GitHub Issue client, no GitLab WorkItem client, no cross-forge backlog
federation, no automatic backlog migration and no bidirectional
GitHub/GitLab synchronization. Those are explicit non-goals of the frozen
architecture, not deferred work.

## Rejected alternatives

- **Provider API clients in the neutral layer** (`PyGithub`-style). Rejected:
  credentials, dialects and remote authority would enter a layer whose entire
  value is purity; the resolver would become untestable without network.
- **A remote claim service or lock service.** Rejected: AGENTS policy forbids
  lock services; GitHub/GitLab state is the lock.
- **Claim leases, heartbeats, age-based expiration.** Rejected: they infer
  abandonment from time, and time is not authority. Issue #33 stays
  independent.
- **Retrying an `UNCERTAIN` POST.** Rejected: a duplicate claim is worse than
  a stuck one; the marker search resolves uncertainty without a second POST.
- **Preferring `origin` over `upstream` on a fork.** Rejected: guessing is how
  a claim lands on the wrong backlog.
- **Journaling after the POST** (or not at all). Rejected: loses exactly the
  fact needed after a crash.
- **Storing claim attempts inside Verified records.** Rejected: the journal is
  non-authoritative; a Verified surface must not carry it.

## Consequences

- PR-2 (#163) implements the neutral policy documents, the pure resolver, the
  identity grammar and the journal; the existing claim-resolution behavior
  (ADR-era `claim_resolution.py`) is preserved as the GitHub mapping of the
  neutral rule.
- Harnesses/skills keep owning remote mutations and must surface canonical
  event identifiers; a harness that cannot is honest degradation (refusal),
  not silent guessing.
- The repository's own GitHub workflow keeps working unchanged through the
  mapping; nothing about this repository's maintenance changes.
- Distributed policy becomes provider-neutral; `templates/AGENTS.md` speaks
  Work Authority; GitHub remains the reference mapping.
