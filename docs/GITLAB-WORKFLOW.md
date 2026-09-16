# GitLab Workflow — the GitLab.com mapping

The generic rules — vocabulary, lifecycle, claims, MERGE_READY, DONE, review
scope, deferred work — live in [`FORGE-WORKFLOW.md`](FORGE-WORKFLOW.md). This
file records only what is GitLab-specific. GitLab Self-Managed is not a
declared V1 target: it stays `UNTESTED` until qualified (ADR-0019).

## Records

| Generic concept | GitLab record |
|---|---|
| WorkItem | issue (work item) |
| ChangeRequest | merge request |
| Backlog state | labels (e.g. `type:*`, `priority:*`), milestones, boards |
| Review state | MR approval; merge when pipeline succeeds, per project settings |
| Completion | issue closed; board/list membership |

GitLab calls its unit of work a *work item* natively; the generic vocabulary
uses the same word deliberately — the mapping is nearly identity for records,
and the interesting differences are claim signals and templates.

## Claim signals

```text
preferred: assign the issue to the claiming account
fallback:  a note on the issue: "Claiming this work item for implementation."
```

The canonical event kinds are `note` (GitLab notes are comments) and
`assignment`. A claim event's stable identifier is the note's id or the
assignee-change event id; the claimant principal is
`gitlab:principal:<stable-account-id>` (the numeric user id, not the username —
a username can be renamed). Timestamps arrive with a zone; normalize with
`to_utc`.

The resolution rule itself (earliest valid claim, deterministic ordering) is in
`FORGE-WORKFLOW.md`; no GitLab-specific resolution exists.

## Templates

`gitlab-templates` (feature `forge-gitlab`, ADR-0017) installs individual
managed files from `templates/gitlab/`:

```text
.gitlab/issue_templates/bug.md
.gitlab/issue_templates/feature.md
.gitlab/merge_request_templates/default.md
```

They are `MANAGED_MUTABLE`: a re-install updates a file still holding the
bytes the stack wrote, preserves a file the user edited (as a conflict), and
never adopts a file it did not write. The GitLab provider itself (release
distribution through the GitLab Releases API and the Generic Package Registry)
is defined by ADR-0019 and implemented by PR-5; this document covers work
management, not release distribution.
