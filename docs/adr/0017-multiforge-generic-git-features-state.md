# ADR-0017 — Multi-Forge I: Generic Git, features, and state V2

- Status: accepted
- Date: 2026-09-16
- Alias: ADR-MF-01
- Materializes: Multi-Forge v1.3.2-final (frozen architecture), §15–16; the
  accepted design gate #23.
- Constrains: `ainative/lifecycle/state.py`, `manifest.py`, `planner.py`,
  `installer.py`, `ainative/lifecycle/data/profiles.json` and
  `components.json`, the feature CLI, `templates/gitlab/`.
- Does not modify: ADR-0009 (ownership and transaction rules are extended, not
  reopened); ADR-0001 through ADR-0016; the Verified authority architecture.

## Context

The lifecycle layer was built GitHub-shaped without saying so. `standard`
installs a `github-templates` component; the distributed workflow policy is
`docs/GITHUB-WORKFLOW.md`; nothing in the state records which forge a project
works with, because there was only one.

Multi-Forge makes the base product **Generic Git**: a project with no forge at
all must be fully supported, GitHub.com and GitLab.com become optional
capabilities, and the two must never be active at the same time — two work
forges in one project means two conflicting authorities over the same facts.
Issue #23 raised the same question from the governance side: profiles are a
governance level, while capabilities (Vault, skills, templates, work-issue
templates) are optional and combine freely. The current manifests conflate the
two.

Three constraints from the existing architecture bound any solution:

1. **One state file, written last.** ADR-0009 §4: `.ai-native/lifecycle/
   state.json` is the only record of what the stack owns, and a transaction
   commits it after every file change, never before.
2. **One transaction system.** The journal, backup, repair and rollback
   machinery of `transaction.py` is the only mutation path; a feature switch is
   not allowed to invent a second one.
3. **Migrations preserve user data.** A migration must be idempotent, must not
   resurrect a previously managed file the user (or a previous uninstall)
   removed, and must not adopt a file the stack never wrote.

## Decision

### 1. Generic Git is the product; forges add capabilities, not authority

A project is a Git project first. Nothing in the lifecycle layer may require a
forge, resolve a forge from a remote URL, or reach a forge API. The lifecycle
layer installs files and records ownership; a forge feature only decides which
forge-shaped files (templates, policy mapping) are installed. Work-authority
questions remain owned by the skills/harnesses that already own them (ADR-MF-02).

### 2. Profiles and features are orthogonal

A **profile** remains what ADR-0009 made it: a governance level (`standard`,
`verified`) that resolves to a component set, with `verified` extending
`standard`. A **feature** is an optional project-scope capability that can be
enabled or disabled independently of the profile. Neither is defined in terms
of the other:

```text
profile  = standard | verified          # governance level
features = forge-github | forge-gitlab  # optional capabilities (V1)
```

Any future capability that installs files into the project becomes a feature
under this model; the model is not extended to capabilities owned at machine
scope (§9).

### 3. The feature model

A feature declares exactly:

| Field | Meaning |
|---|---|
| `name` | stable ID (`forge-github`, `forge-gitlab`), never localised, never positional |
| `scope` | `project` in V1; a machine-scope entry is not a feature |
| `components[]` | component IDs from `components.json` the feature installs |
| `conflicts[]` | feature names that may not be active at the same time |

`forge-github` conflicts with `forge-gitlab`, and the manifest marks work-forge
features as such: **at most one work-forge feature may be active**. Zero is
valid (`feature switch none`, the Generic Git shape). A V2 state that names two
work forges is refused with `STATE_CONFLICTING_WORK_FORGE_FEATURES` — at load,
before planning, never by silently picking one.

### 4. State schema V2 and the single projection

`state.json` gains `schema_version: 2` and one new array:

```text
active_features: ["forge-github"]     # 0..1 work forge; empty is valid
```

Every read path — `doctor`, `status`, `planner`, `feature status`,
`update check` — derives its view through one shared function,
`project_install_state()`. It returns the effective V2 state for a project and
is the only place that knows how to project older schemas:

- `schema_version: 1` → effective V2 with the **`forge-github` compatibility
  default**: a legacy project is a GitHub project until it explicitly switches.
  This is a projection, not a write.
- `schema_version: 2` → validated as-is (work-forge conflict refusal above).

The projection never writes, never caches, and is never bypassed by a command
that wants "just the profile". One owner, or the read paths drift.

### 5. Migration is state-last, idempotent, and never resurrects absence

A mutating operation on a V1 project (init, update, feature command) migrates
the state inside the existing transaction: files first, then the V2 state,
then commit. A failure before the commit leaves the V1 state untouched; a
completed commit leaves a complete V2 state — a serialized half-V2 state is
never produced.

Migration rules:

- `github-templates` keeps its component ID and its managed-file records.
  `gitlab-templates` is added as a new component (`templates/gitlab/` →
  `.gitlab/`, individual files, `MANAGED_MUTABLE`, same ownership semantics as
  the GitHub templates).
- A previously managed file that is now absent stays absent. Migration does not
  re-create it, and no tombstone records its absence: absence is not a fact
  worth a permanent file. A later explicit `feature enable` may seed its
  feature's files through the normal install path.
- Running the migration twice changes nothing the second time (idempotence is
  tested, not assumed).

### 6. Switching is one lifecycle transaction

`feature enable`, `feature disable`, `feature switch <name>` and
`feature switch none` run inside the existing per-project lifecycle lock and
the existing transaction engine, in this order:

```text
acquire the project lifecycle lock
reload state            → project effective V2
plan                    → feature deltas + ownership decisions
apply                   → files
verify
write the V2 state last
commit
```

`feature switch X` is `disable current work forge + enable X` as one plan, so
an interruption cannot leave a project with two forge feature sets or with
none where it had one. A conflict (`enable` a feature that conflicts with an
active one) is refused before planning; the remedy is `switch`, and the
refusal says so.

### 7. CLI surface

```text
ainative feature status
ainative feature enable <name>
ainative feature disable <name>
ainative feature switch <name>
ainative feature switch none
```

`feature status` is read-only and derives from `project_install_state()`.

### 8. Ownership is inherited, not redefined

Features add no new ownership kind. The ADR-0009 matrix applies unchanged:
managed-and-unmodified → replace/update allowed; managed-and-modified →
preserve, reported as a conflict; never-managed → never silently adopted; a
user collision → conflict; a removed feature's modified file → preserved. A
round trip (GitHub → GitLab → none → GitHub) loses no user data, and that is an
executable test, not a promise.

### 9. Machine-scope capabilities are not features

Harness instruction files (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, …),
machine manifests, vault bindings, and the global skills trees are
machine-scope integration. They stay owned by `ainative machine` /
`scripts/install_agents.py` and do not appear in `active_features`. A
capability spanning both scopes is split: its project files can become a
feature, its machine files stay machine-managed.

### 10. Dogfood, and what stays GitHub-specific

This repository's own root `AGENTS.md` is GitHub-specific on purpose (its own
workflow is GitHub's) and is never a target of the generic distributed policy
template; the distributed generic template is a different artifact (the
distributed policy template, `templates/AGENTS.md`, PR-2). Feature machinery
and the `gitlab-templates` addition must not rewrite the stack repository's own
`.github/` files or `AGENTS.md`.

GHES and GitLab Self-Managed are **not** features in V1 and are not declared
supported: the model leaves room for them, qualification does not exist.

## Rejected alternatives

- **Extend profiles into capability bundles** (`standard+forge-gitlab`, …).
  Rejected: profiles and capabilities change for different reasons and at
  different rates; a matrix of combined profiles multiplies the manifest and
  makes "which governance am I under?" unanswerable from the state alone.
- **Per-forge state files** (`forge-github.json`, `forge-gitlab.json`).
  Rejected: two files can disagree, and the whole point of one state file
  written last is that it cannot.
- **Detect the forge from the Git remote and activate implicitly.** Rejected:
  a remote URL is not an authority fact; detection is diagnostic (PR-3), never
  a mutation trigger.
- **File tombstones for legacy files that are absent.** Rejected: records a
  negative forever, for a state (absence) that is already the truth.
- **A second transaction path for feature switches.** Rejected: ADR-0009's
  journal/backup/repair/rollback exists; duplicating it doubles the recovery
  surface.
- **Adopting user-created templates as feature files.** Rejected: adoption is
  how the stack would later delete or overwrite the user's file.

## Consequences

- `state.py` gains schema V2 and `project_install_state()`; every reader is
  migrated to it in the same change, so no path reads `active_profile` and
  guesses features.
- A state migrated to V2 requires a runtime that understands V2. The existing
  schema guard already refuses a newer schema (`INSTALL_STATE_CORRUPTED`:
  "upgrade the CLI rather than downgrading state"), so the migration is a
  documented breaking behavior change, not a silent one.
- `github-templates` keeps its ID; `gitlab-templates` is new; the GitLab
  template files are the GitLab equivalents of the existing GitHub ones.
- PR-1 (#162) implements this ADR; PR-3 (#164) consumes the projection for
  observation; ADR-MF-02 (ADR-0018) builds the provider-neutral workflow on
  top of the feature/project model.
- The projection is the single owner of legacy semantics; a bug fixed there is
  fixed everywhere at once.
