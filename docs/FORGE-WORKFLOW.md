# Forge Workflow — provider-neutral work management

How AI agents and humans turn ideas into merged, verified work when the work
authority may be GitHub, GitLab, or nothing at all (Generic Git). This file is
the canonical statement of the *generic* rules; each provider's mechanics live
in its mapping — [`GITHUB-WORKFLOW.md`](GITHUB-WORKFLOW.md),
[`GITLAB-WORKFLOW.md`](GITLAB-WORKFLOW.md) — and where a mapping is silent, this
file decides. The architecture review for this document is closed; change it
through an Issue, not by silently editing policy.

## Vocabulary

```text
Work Authority   the remote whose work records are authoritative for a project:
                 one provider + one project identity. Not a URL, not a hostname.
WorkItem         the unit of work on that authority  (GitHub Issue, GitLab WorkItem)
ChangeRequest    the reviewable change               (GitHub PR,    GitLab merge request)
WorkAuthorityRef provider + stable project identity  (never guessed from a hostname)
Claim            an agent's remote signal that it owns a WorkItem
```

One provider, one project, at most: a project has **one** work authority. Two
candidates that disagree (a fork's `origin` and `upstream`) are *ambiguity*, and
ambiguity stops remote mutation — see "Work Authority resolution" below.

## Where state lives

```text
Work authority records  = canonical actionable backlog (WorkItems and their state)
Provider metadata       = labels, milestones, review state (per mapping)
ADRs                    = accepted architecture (in the repository)
Work Contracts          = deterministic verification when policy requires them
Vault / Obsidian        = historical context only
Skills                  = procedures
```

AI Native never stores project-specific backlog state: no `issues.json`, no
current-milestone file, no vault board mirroring the authority. If the work
authority is unreachable, the backlog is unreachable with it — that is the
point: one authoritative source per fact.

### WorkItem vs ADR

An ADR records an architecture decision already made. A WorkItem records work
that should happen. "Refactor X per ADR-0007" may be a WorkItem; disagreeing
with ADR-0007 is not — it is a proposal to amend the ADR, handled like any
architectural change (WorkItem first, then a deliberate ADR update).

### WorkItem vs Work Contract

A Verified Work Contract is the deterministic proof side of one unit of work:
constrained verification, evidence provenance, convergence. It does not
replace the WorkItem; it verifies it. When repository policy requires Verified
work, the issue-to-implementation skill creates or updates the contract after
the claim and binds the WorkItem's acceptance criteria into it.

### WorkItem vs Vault memory

The Vault keeps session summaries, research, postmortems, decision context and
links (WorkItem, ChangeRequest, ADR). It must never hold canonical current
state: no current backlog, no status mirrors, no live Kanban, no assignee
snapshots. No bidirectional Vault ↔ authority synchronization exists or should
exist.

## Lifecycle of one unit of work

```text
finding --> triage --> WorkItem (or rejected / Discussion / ADR candidate)
                          |
                          v
              issue-to-implementation
              claim -> branch -> implement -> validate
                          |
                          v
                ChangeRequest with "Refs #N"
                          |
                          v
            MERGE_READY (all conditions)
                          |
                          v
      Refs #N -> Closes #N  -->  FINAL_MERGE_FRESHNESS
                          |
                          v
                merge (authorized process)
                          |
                          v
      WorkItem closed as completed --> provider state = Done
```

### Triage

Ideas, bugs, audit findings and research observations are candidates, not
backlog. Triage validates, deduplicates, classifies and decides: WorkItem,
Discussion, ADR candidate, or reject. Only useful, actionable work is
persisted. Triage never implements code.

### Implementation

One skill owns the path from a claimed WorkItem to a merged ChangeRequest. Its
invariants:

1. **Claim before working.** See "Claims" below.
2. **Scope is the WorkItem.** Implement only its canonical scope.
3. **Acceptance Criteria are protected.** An implementation agent MUST NOT
   weaken, remove, replace or materially reinterpret acceptance criteria to
   make its implementation pass. It MAY detect ambiguity, identify
   infeasibility, propose a change or request clarification — but a material
   change becomes authoritative only after explicit approval from an
   authorized maintainer **and** persistence in the WorkItem. Material =
   required behavior, functional scope, security requirements, performance
   thresholds, supported platforms, failure behavior, public API/contract,
   acceptance thresholds. If uncertain, treat it as material and ask. There is
   no separate AC database: the WorkItem body is the only home of the AC.
4. **Policy conflicts stop work.** Root `AGENTS.md` is the repository baseline;
   local `AGENTS.md` files specialize or strengthen it and must never silently
   weaken it. A real contradiction is surfaced as a visible conflict — never
   resolved silently.
5. **Refs while working, Closes when ready.** Open and update ChangeRequests
   with `Refs #N` during development. `Closes #N` appears only once
   MERGE_READY is satisfied, and only immediately before the merge.

After canonical scope and AC are bound, implementation choices use
`implementation-economy`; it cannot alter scope or acceptance criteria.

### MERGE_READY

`MERGE_READY` is a checklist, not a merge:

```text
MERGE_READY =
    current WorkItem acceptance criteria satisfied
  + required tests/checks pass
  + documentation updated where required
  + review requirements satisfied
  + no relevant blocker
  + Verified CONVERGED when policy requires it
  + WorkItem scope/AC freshness confirmed
```

### FINAL_MERGE_FRESHNESS

Immediately before the actual merge, re-read the WorkItem and its current
acceptance criteria and compare against the latest validated snapshot (Verified
work: compare the canonical AC digest with the digest bound in the Work
Contract). A material difference invalidates MERGE_READY: `ISSUE_CHANGED` — do
not merge, do not close, reconcile scope and verify again. This is not an
atomic remote transaction; it is the freshest possible pre-merge check. It
exists because the WorkItem is shared state and another actor may have changed
it while the ChangeRequest was in review.

### DONE

```text
DONE = MERGE_READY was valid
     + ChangeRequest merged
     + WorkItem closed as completed
     + provider state = Done (when the mapping defines one)
```

Closed is not Done: WorkItems are closed as duplicate, not-planned, invalid or
superseded too. Only "closed as completed" after a merged ChangeRequest counts.
If the provider exposes a completion state but the automation lacks permission
to update it, report `PROJECT_STATUS_SYNC_REQUIRED` instead of claiming Done
silently.

## Work Authority resolution

Reading and mutating remote state is the harness's job (it holds the provider
tooling and the credentials). `ainative` adds one pure local resolver,
`resolve_observed_work_authority()` (`ainative/forge.py`): no network, no
credentials, no writes, no push authorization. Priority:

```text
1. an explicit WorkItem/ChangeRequest repository reference
2. an explicit harness-declared authority
3. exactly one compatible observed candidate
4. otherwise: WORK_AUTHORITY_UNAVAILABLE | WORK_AUTHORITY_AMBIGUOUS | WORK_AUTHORITY_MISMATCH
```

Observed candidates are diagnostic only. `github.com` and `gitlab.com` are the
only hosts whose provider is a fact; a self-hosted host is `unknown`, never
inferred from its name. When the resolution is ambiguous, remote mutation stops
— diagnostics may continue.

## Claims

There is no distributed lock and no lock service. A claim is a remote signal
and a local record:

- **Preferred signal:** assignment. **Fallback:** an explicit claim comment or
  note. The mapping names the provider's exact signals.
- **Identity is canonical**, never local formatting:
  `<provider>:principal:<stable-provider-id>` for the claimant,
  `<provider>:<event-kind>:<stable-event-id>` for the event (`comment`, `note`,
  `assignment`). Timestamps are normalized to UTC. Winner ordering is the total
  order `(created_at_utc, canonical_event_identifier)`; an unorderable pair is
  `CLAIM_CONFLICT` and every claimant stops.
- **Before claiming**, read the WorkItem and any linked active ChangeRequest: a
  linked open implementation ChangeRequest is a claim-level conflict
  (`ACTIVE_PR_CONFLICT`) — stop, unless a maintainer requested a competing
  attempt or the ChangeRequest was explicitly abandoned.
- **Journal before POST.** `ainative claim-attempt` writes a PENDING record
  under `.ai-native/state/claim-attempts/` *before* the remote signal, with a
  deterministic marker the signal must carry. A journal that cannot be written
  is `CLAIM_JOURNAL_UNAVAILABLE` and no signal is sent.
- **Outcomes:** `CONFIRMED`, `LOST`, `CONFLICT`, `UNCERTAIN`, `ABANDONED`. An
  unknown POST result is `UNCERTAIN` and is **never** retried automatically:
  the marker search on the remote is the only resolution. A corrupt journal
  fails closed.
- **Abandonment is explicit:** `ainative claim-attempt abandon <id> --confirm`
  is a local transition that keeps the record; only then may a new attempt be
  created. No leases, no heartbeats, no age-based expiration: time is not
  authority.

## Review scope

A ChangeRequest review checks: the WorkItem's acceptance criteria, the relevant
`AGENTS.md` policy, the relevant ADRs, and regressions the change introduces or
worsens. Anything else found during review is handled by priority and never
expands the current change:

```text
P0/P1  -> separate WorkItem / escalation; may block a release globally,
          does not expand the change
P2/P3  -> backlog candidate; does not expand the change
```

Only a finding caused or worsened by the current change — or one that directly
makes its merge unsafe — may block that change.

## Deferred work

Significant deferred work must not live only in chat, a temporary plan, or
historical memory. If it is actionable and worth retaining, it becomes a
WorkItem; if it was explicitly rejected, no WorkItem is created.

## Branch naming

Recommended, where the provider allows free branch names:

```text
feat/<id>-description   fix/<id>-description
docs/<id>-description   refactor/<id>-description
chore/description       # truly trivial internal work, no WorkItem required
```

Naming is a convention, not an enforcement mechanism.

## Mappings

| Concept | GitHub | GitLab |
|---|---|---|
| WorkItem | Issue | WorkItem (issue) |
| ChangeRequest | Pull request | Merge request |
| Claim signal | assignment, issue comment | assignee, note |
| Claim event id | comment/assignment event id | note/assignment id |
| Review state | PR review | MR approval |
| Templates | `templates/github/` → `.github/` | `templates/gitlab/` → `.gitlab/` |

Each mapping document records its provider's exact mechanics and points back
here for the rules. `github-templates` and `gitlab-templates` are the two
feature components that install them (ADR-0017).
