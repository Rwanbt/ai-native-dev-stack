# GitHub Workflow — AI-centered work management

How AI agents and humans turn ideas into merged, verified work using GitHub as
the canonical active state. The architecture review for this document is
closed; change it through an issue, not by silently editing policy.

## Where state lives

```text
GitHub Issues      = canonical actionable backlog
GitHub Project     = operational visualization when configured
Milestones         = delivery grouping
ADRs               = accepted architecture
Work Contracts     = deterministic verification when policy requires them
Vault / Obsidian   = historical context only
Skills             = procedures (github-triage, issue-to-implementation,
                     implementation-economy)
```

AI Native never stores project-specific backlog state. There is no
`issues.json`, no `current-milestone.json`, no vault board that mirrors GitHub.
If GitHub is unreachable, the backlog is unreachable with it — that is the
point: one authoritative source per fact.

### Issue vs Project

An Issue is the work item: problem, expected outcome, acceptance criteria.
A Project (when a repository configures one) is a view over Issues, with two
canonical operational fields:

| Field  | Values                                             |
|--------|----------------------------------------------------|
| Status | `Inbox`, `Backlog`, `Ready`, `In Progress`, `Done` |
| Area   | project-specific metadata (subsystem, domain)      |

Do not add `Priority`, `Type`, `Effort`, or `Review` fields in v1. Type and
priority are Issue labels (`type:bug`, `priority:P1`, ...) — labels travel with
the Issue everywhere, Project fields do not. PR state stays GitHub's native PR
state; it is not a Project column.

A repository without a Project loses nothing but the visualization. Every
skill must degrade gracefully when no Project exists: Issues, labels and PRs
are the whole workflow for small repositories. Never fail because a Project is
absent.

### Issue vs ADR

An ADR records an architecture decision already made. An Issue records work
that should happen. "Refactor X per ADR-0007" may be an Issue; disagreeing
with ADR-0007 is not — it is a proposal to amend the ADR, handled like any
architectural change (issue first, then a deliberate ADR update).

### Issue vs Work Contract

A Verified Work Contract is the deterministic proof side of one unit of work:
constrained verification, evidence provenance, convergence. It does not
replace the Issue; it verifies it. When repository policy requires Verified
work, the issue-to-implementation skill creates or updates the contract after
the claim and binds the Issue's acceptance criteria into it.

### Issue vs Vault memory

The Vault keeps session summaries, research, postmortems, decision context and
links (Issue, PR, ADR). It must never hold canonical current state: no current
backlog, no Issue status mirrors, no live Kanban, no assignee snapshots. No
bidirectional Vault <-> GitHub synchronization exists or should exist.

## Lifecycle of one unit of work

```text
finding --> github-triage --> Issue (or rejected / Discussion / ADR candidate)
                                  |
                                  v
                     issue-to-implementation
                     claim -> branch -> implement -> validate
                                  |
                                  v
                        PR with "Refs #N"
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
              Issue closed as completed --> Project Status = Done
```

### Triage (skills/github-triage)

Ideas, bugs, audit findings and research observations are candidates, not
backlog. Triage validates, deduplicates, classifies (`type:*`, `priority:P*`)
and decides: Issue, Discussion, ADR candidate, or reject. Only useful,
actionable work is persisted. P0/P1 validated findings may be escalated into
Issues when authorized; P2 findings may become Issues when useful; P3 and
research notes are not automatically created as Issues. Triage never
implements code.

### Implementation (skills/issue-to-implementation)

One skill owns the path from a claimed Issue to a merged PR. Its invariants:

1. **Claim before working.** See "Multi-agent claims" below.
2. **Scope is the Issue.** Implement only the Issue's canonical scope.
3. **Acceptance Criteria are protected.** An implementation agent MUST NOT
   weaken, remove, replace or materially reinterpret an Issue's Acceptance
   Criteria to make its implementation pass. It MAY detect ambiguity,
   identify infeasibility, propose a change or request clarification — but a
   material AC change becomes authoritative only after explicit approval from
   an authorized maintainer/user **and** persistence in the GitHub Issue.
   Material changes include: required behavior, functional scope, security
   requirements, performance thresholds, supported platforms, failure
   behavior, public API/contract, acceptance thresholds. If uncertain, treat
   the change as material and ask. There is no separate AC database: the
   Issue body is the only home of the AC.
4. **Policy conflicts stop work.** Root AGENTS.md is the repository baseline;
   local AGENTS.md files specialize or strengthen it and must never silently
   weaken it. A real contradiction is surfaced as a visible conflict (on the
   Issue when working from one: conflicting files, conflicting rules, why
   implementation cannot proceed safely) — never resolved silently. ADRs and
   AGENTS.md govern different domains; a genuine contradiction between them
   requires reconciliation, not arbitrary precedence.
5. **Refs while working, Closes when ready.** Open and update PRs with
   `Refs #N` during development. `Closes #N` appears only once MERGE_READY is
   satisfied, and only immediately before the merge.

After canonical scope and AC are bound, implementation choices use
`implementation-economy`; it cannot alter Issue scope or Acceptance Criteria.

### MERGE_READY

`MERGE_READY` is a checklist, not a merge:

```text
MERGE_READY =
    current Issue acceptance criteria satisfied
  + required tests/checks pass
  + documentation updated where required
  + review requirements satisfied
  + no relevant blocker
  + Verified CONVERGED when policy requires it
  + Issue scope/AC freshness confirmed
```

### FINAL_MERGE_FRESHNESS

Immediately before the actual merge, re-read the Issue and its current
acceptance criteria and compare against the latest validated snapshot
(Verified work: compare the canonical AC digest with the digest bound in the
Work Contract). A material difference invalidates MERGE_READY:
`ISSUE_CHANGED` — do not merge, do not close, reconcile scope and verify
again.

This is not an atomic GitHub transaction; it is the freshest possible
pre-merge check. It exists because the Issue is shared state and another
actor may have changed it while the PR was in review.

### DONE

```text
DONE = MERGE_READY was valid
     + PR merged
     + Issue closed as completed
     + Project Status = Done   (when a Project is configured)
```

Closed is not Done. Issues are closed as `duplicate`, `not planned`,
`invalid` or `superseded` too — only "closed as completed" after a merged PR
counts as Done. If a Project exists but the automation lacks permission to
update it, report `PROJECT_STATUS_SYNC_REQUIRED` instead of claiming Done
silently.

## Multi-agent claims

There is no distributed lock and no lock service. The claim is GitHub state:

- **Preferred:** GitHub Issue assignment.
- **Fallback** (actor cannot assign): an explicit Issue claim comment, e.g.
  "Claiming this Issue for implementation."

Valid claim signals normalize to: `actor`, `created_at`,
`stable_github_identifier` (comment or assignment event ID), `claim_kind`.
Before claiming, also read the open PRs that reference or implement the
Issue (PR body `Refs`/`Closes`/`Fixes`, issue timeline links, or an explicit
"implements #N"): **an active linked implementation PR is a claim-level
conflict** (`ACTIVE_PR_CONFLICT` -> STOP). It lifts only when explicit: a
maintainer requested a competing implementation or collaboration, the PR was
explicitly abandoned or superseded, or the same actor is continuing their own
implementation. Age alone never proves abandonment; an ambiguous
relationship is surfaced, not duplicated around. After claiming, re-read the
Issue — the claim is only as good as the freshest read, and a PR that
appeared during the race re-triggers the conflict.

Resolution (implemented by
`skills/issue-to-implementation/bin/claim_resolution.py`):

```text
0 valid claims   -> CLAIM_FAILED    -> nobody proceeds
1 valid claim    -> that claimant proceeds
>1 valid claims  -> deterministic winner:
                     each actor stands at their EARLIEST valid claim event
                     (a later assignment never rewrites an earlier comment),
                     actors sort by created_at ascending,
                     then stable identifier ascending;
                   first proceeds, all others STOP
unorderable      -> CLAIM_CONFLICT  -> every claimant STOPs
```

Assignment preference is an acquisition rule, not an arbitration override.
Stale-claim expiration, stale-PR expiration, heartbeats and leases are out
of scope in v1.

## Review scope

A PR review checks: the Issue's acceptance criteria, the relevant AGENTS.md
policy, the relevant ADRs, and regressions the PR introduces or worsens.
Anything else found during review is handled by priority and never expands
the current PR:

```text
P0/P1  -> separate Issue / escalation; may block a release globally,
          does not expand the PR
P2/P3  -> backlog candidate (github-triage); does not expand the PR
```

Only a finding caused or worsened by the current PR — or one that directly
makes its merge unsafe — may block that PR.

## Deferred work

Significant deferred work must not live only in chat, a temporary plan, or
historical memory. If it is actionable and worth retaining, it becomes a
GitHub Issue; if it was explicitly rejected, no Issue is created.

## Branch naming

Recommended:

```text
feat/123-description   fix/123-description
docs/123-description   refactor/123-description
chore/description      # truly trivial internal work, no Issue required
```

Naming is a convention, not an enforcement mechanism, in v1.

## Templates

Generic templates ship with the stack (`templates/github/`) and are installed
as managed files (individual files, never the whole `.github/` directory):

- `.github/ISSUE_TEMPLATE/bug.md` — Problem, Reproduction, Expected outcome,
  Acceptance criteria, Affected surface (triage hint only; Project Area is
  canonical when a Project is used).
- `.github/ISSUE_TEMPLATE/feature.md` — Problem, Expected outcome,
  Acceptance criteria, Out of scope.
- `.github/PULL_REQUEST_TEMPLATE.md` — What changed, Why, Refs #, Validation,
  Risk. It deliberately contains no `Closes`: development starts with `Refs`.

Ownership follows the lifecycle rules: a pre-existing template the user wrote
is preserved; a stack-installed template the user modified is preserved and
reported as a conflict; a stack-installed, unmodified template may be updated
or removed by update/uninstall. See `tests/test_lifecycle_github_templates.py`
for the executable contract.
