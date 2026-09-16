# GitHub Workflow — the GitHub.com mapping

The generic rules — vocabulary, lifecycle, claims, MERGE_READY,
FINAL_MERGE_FRESHNESS, DONE, review scope, deferred work, branch naming — live
in [`FORGE-WORKFLOW.md`](FORGE-WORKFLOW.md), with the GitLab mapping in
[`GITLAB-WORKFLOW.md`](GITLAB-WORKFLOW.md). This file records only what is
GitHub-specific. The architecture review for this document is closed; change
it through an Issue, not by silently editing policy.

## Where GitHub state lives

```text
GitHub Issues      = canonical actionable backlog
GitHub Project     = operational visualization when configured
Milestones         = delivery grouping
```

AI Native never stores project-specific backlog state. There is no
`issues.json`, no `current-milestone.json`, no vault board that mirrors
GitHub. If GitHub is unreachable, the backlog is unreachable with it — that is
the point: one authoritative source per fact. (The generic statement, and the
WorkItem vs ADR / Work Contract / Vault memory rules, are in
`FORGE-WORKFLOW.md`.)

### Issue vs Project

An Issue is the work item: problem, expected outcome, acceptance criteria.
A Project (when a repository configures one) is a view over Issues, with two
canonical operational fields:

| Field  | Values                                             |
|--------|----------------------------------------------------|
| Status | `Inbox`, `Backlog`, `Ready`, `In Progress`, `Done` |
| Area   | project-specific metadata (subsystem, domain)      |

Do not add `Priority`, `Type`, `Effort`, or `Review` fields: Type and priority
are Issue labels (`type:bug`, `priority:P1`, ...) — labels travel with the
Issue everywhere, Project fields do not. PR state stays GitHub's native PR
state; it is not a Project column.

A repository without a Project loses nothing but the visualization. Every
skill must degrade gracefully when no Project exists: Issues, labels and PRs
are the whole workflow for small repositories. Never fail because a Project is
absent.

## Claim signals

```text
preferred: assign the Issue to the claiming account
fallback:  an explicit Issue comment:
           "Claiming this Issue for implementation."
```

Valid claim signals normalize to: `actor`, `created_at`,
`stable_github_identifier` (comment or assignment event ID), `claim_kind`.
Before claiming, also read the open PRs that reference or implement the Issue
(PR body `Refs`/`Closes`/`Fixes`, issue timeline links, or an explicit
"implements #N"): **an active linked implementation PR is a claim-level
conflict** (`ACTIVE_PR_CONFLICT` -> STOP). It lifts only when explicit: a
maintainer requested a competing implementation or collaboration, the PR was
explicitly abandoned or superseded, or the same actor is continuing their own
implementation. Age alone never proves abandonment; an ambiguous relationship
is surfaced, not duplicated around. After claiming, re-read the Issue — the
claim is only as good as the freshest read, and a PR that appeared during the
race re-triggers the conflict.

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
Stale-claim expiration, stale-PR expiration, heartbeats and leases are out of
scope in v1 (issue #33 stays independent). The journal-before-POST rule and
the recovery surface (`ainative claim-attempt`) are in `FORGE-WORKFLOW.md`.

## Implementation, on GitHub

The generic invariants — claim before working, scope is the Issue, protected
acceptance criteria, policy conflicts stop work, `Refs` while working and
`Closes` only when ready — are stated once in `FORGE-WORKFLOW.md`. After scope
and AC are bound, implementation choices use `implementation-economy`; its
limits are stated there too.

## MERGE_READY and DONE, on GitHub

`MERGE_READY` and `FINAL_MERGE_FRESHNESS` are defined once in
`FORGE-WORKFLOW.md`; on GitHub the linkage mechanics are:

- PRs start with `Refs #N`; `Closes #N` appears only once MERGE_READY holds,
  only immediately before the merge;
- DONE additionally requires the Project Status to be `Done` when a Project is
  configured;
- if the automation lacks permission to update the Project, report
  `PROJECT_STATUS_SYNC_REQUIRED` instead of claiming Done silently.

## Templates

Generic templates ship with the stack (`templates/github/`) and are installed
as managed files (individual files, never the whole `.github/` directory) by
the `github-templates` component, owned by the `forge-github` feature
(ADR-0017):

- `.github/ISSUE_TEMPLATE/bug.md` — Problem, Reproduction, Expected outcome,
  Acceptance criteria, Affected surface (triage hint only; Project Area is
  canonical when a Project is used).
- `.github/ISSUE_TEMPLATE/feature.md` — Problem, Expected outcome, Acceptance
  criteria, Out of scope.
- `.github/PULL_REQUEST_TEMPLATE.md` — What changed, Why, Refs #, Validation,
  Risk. It deliberately contains no `Closes`: development starts with `Refs`.

Ownership follows the lifecycle rules: a pre-existing template the user wrote
is preserved; a stack-installed template the user modified is preserved and
reported as a conflict; a stack-installed, unmodified template may be updated
or removed by update/uninstall. See `tests/test_lifecycle_github_templates.py`
for the executable contract.

## Review scope

The generic rule (only findings caused or worsened by the current change may
block it; P0/P1 escalate separately, P2/P3 become backlog candidates) is stated
once in `FORGE-WORKFLOW.md`.
