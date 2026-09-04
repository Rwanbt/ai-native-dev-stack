# ADR-0009 — Distribution profiles and lifecycle ownership

- Status: accepted
- Date: 2026-09-04
- Constrains: `install.py`, `install.sh`, `install.ps1`,
  `scripts/stack-update-check.sh`, `scripts/stack-upgrade.sh`, `UPDATING.md`.
- Does not modify: ADR-0001 through ADR-0008. The Verified Work Plane's
  authority architecture is closed and is not reopened here.

## Context

The stack shipped two installers and one updater that did not know about each
other:

| Mechanism | Scope | What it owns | What it can undo |
|---|---|---|---|
| `install.py` | one project | `tools/ai_docs/`, `.claude/skills/`, `.agents/skills/`, `AGENTS.md`, `conventions.json`, `config.sh`, a `.gitignore` line, `.stack-lock.json` | nothing |
| `scripts/install_agents.py` | one machine | six harness instruction files (managed blocks), `~/.agents/skills`, `~/.claude/skills`, three rendered adapter files | one block, via `--no-vault-block` |
| `scripts/stack-upgrade.sh` | the stack clone | the clone's git history | nothing in any project |

Three consequences were observable before this ADR:

1. **No uninstall existed at any level.** Nothing recorded which files the
   stack had written into a project, so nothing could remove them without
   guessing — and guessing means either leaving files behind or deleting a
   user's work.
2. **The project half was never updated.** `stack-upgrade.sh` fast-forwards the
   clone. A project that ran `install.py` in June still holds June's
   `tools/ai_docs/` in September; the only remedy was to re-run the installer,
   which prunes (`copy_tree`) without ever asking whether the user had edited
   the file it is about to delete.
3. **`copy_tree` prunes on the digest of nothing.** It deletes any file under a
   managed directory that the source no longer has. That is correct for files
   the stack wrote and never correct for a file the user added or edited. The
   installer had no way to tell the two apart.

The product now needs two distinct audiences — a Standard profile for learning
and ordinary AI-assisted work, and a Verified profile that adds governed Work
Contracts and deterministic verification. Offering a reversible choice between
them is impossible on top of installers that cannot describe, undo, or update
what they wrote.

## Decision

### 1. Two profiles, by inheritance, resolved from declarative manifests

`standard` is a complete profile. `verified` declares `extends: "standard"` and
adds components; it never restates a Standard component. The resolver computes
`effective_components(verified) = components(standard) + components(verified)`,
in that order, deduplicated, and refuses a cycle or an unknown parent.

The manifests are JSON (`ainative/lifecycle/data/profiles.json`,
`components.json`), read with the standard library. No YAML dependency is added
to read two files.

The inheritance is one-directional at every level: the lifecycle layer may
invoke the Verified Work Plane; the Verified Work Plane must not import the
lifecycle layer; and the Standard profile must not import `trust`,
`authorization`, `evaluator` or `controller` in order to operate. The top-level
CLI dispatcher enforces this by importing `ainative_workplane` lazily, inside
the Verified branch only — a `ainative init --profile standard` never loads an
authority module.

### 2. `active_profile` is a distribution fact, never an authority fact

Writing `verified` into the lifecycle state activates *integration*: it says
which components are installed and which surfaces are wired. It says nothing
about whether the project is trusted. Trust remains what
`.ai-native/trust/project_trust.json` and ADR-0004/0005/0006 say it is.

Concretely, the lifecycle layer is forbidden from writing a trust anchor, an
approval root, an approval, a work contract, a verification run, or a
convergence record. `ainative init --profile verified` prepares the environment
and then *reports* that a human trust bootstrap is still required. It does not
perform the bootstrap: ADR-0006 states the Work Plane cannot verify who ran it,
so an installer that ran it on the user's behalf would be manufacturing the one
fact the architecture refuses to manufacture.

The reverse also holds: Standard never writes a fake convergence, a fake work
contract or a fake trust state to look like Verified.

### 3. Four ownership classes, and a digest per managed file

Every path the lifecycle layer touches is classified before it is written, and
the classification is recorded in the install state together with the digest
the file had at install time:

| Class | Meaning | Update | Uninstall (default) |
|---|---|---|---|
| `MANAGED_IMMUTABLE` | written by the stack, not meant to be edited | replaced only when `digest_current == digest_at_install` | removed only when unchanged |
| `MANAGED_MUTABLE` | written by the stack, the user may edit it | never silently overwritten; a changed file gets a `.new` template beside it and a `CONFLICT` | preserved if changed, removed if unchanged |
| `USER_DATA` | the user's, or the project's history | never touched | never removed; `--purge` only, with explicit intent |
| `EXTERNAL_CONFIG` | a file the stack does not own, into which it wrote a delimited region | only the region is rewritten | only the region is removed; the rest is byte-preserved |

A managed file is classified `UNCHANGED`, `USER_MODIFIED`, `MISSING` or
`CONFLICT` by comparing `digest_at_install` with the digest on disk. A
`USER_MODIFIED` file is never silently deleted or overwritten by any operation.

This is the rule that replaces `copy_tree`'s unconditional prune. Pruning still
happens — a file removed upstream must not survive — but only for a file whose
digest still matches what the stack wrote.

### 4. Every mutation is a transaction, and the state commits last

```
inspect -> plan -> validate -> backup -> stage -> apply -> verify -> commit state
```

The install state is written as the final step of a successful operation. An
interruption therefore leaves the previous valid state on disk, and a journal
entry that says what was in flight. There is no half-installed profile: the
observable end state is the old one or the new one.

The journal lives at `.ai-native/lifecycle/transactions/<id>.json` and moves
through `PREPARED -> APPLYING -> COMMITTED | ROLLED_BACK`, with anything found
in `APPLYING` at the next run classified `INTERRUPTED`. `ainative doctor`
reports it; `ainative repair` completes the deterministic recovery from the
journal's recorded backup.

### 5. Downgrade preserves; only `purge` deletes

`ainative profile switch standard` deactivates Verified integration and leaves
every byte of `.ai-native/trust`, `.ai-native/work` and `.ai-native/runs` in
place. That state becomes **dormant**, not deleted, so
`ainative profile switch verified` can reactivate a project with its audit
trail intact. The historical Work revisions, run evidence and approval records
are never rewritten to make a downgrade or an update succeed.

Deleting Verified data is a separate, explicit command
(`ainative profile purge verified`), which requires `--yes` without a TTY and
prints the exact paths first. `profile switch standard` never implies it.

### 6. No silent auto-update, and no network inside an authority command

The lifecycle layer may **detect** a new release automatically; it may not
**apply** one automatically. A check is cached (default TTL 24 h) at
`.ai-native/lifecycle/update-cache.json`, is bounded by a short timeout, and
treats `OFFLINE` and `CHECK_FAILED` as non-fatal outcomes rather than errors.

`ainative verify`, `ainative converge`, `ainative trust` and `ainative work`
must never trigger a network update check. A verdict-producing command that
reaches the network has added a non-deterministic, externally-controlled input
to an authoritative surface. Those commands may display an already-cached
notice and nothing more; the dispatcher routes them without touching the
updater.

Update integrity is SHA-256 over the release archive, verified before any file
is written, together with archive path-safety checks. This protects against a
corrupted or substituted archive on the wire. It does **not** protect against a
compromised release source, and the documentation says so rather than implying
a guarantee the mechanism does not provide.

### 7. One authority for the lifecycle; the wrappers stay thin

`install.sh` and `install.ps1` remain, because a beginner on a fresh machine
needs an entry point that does not assume a working `pip`. They are reduced to
"find a Python, hand over" and contain no lifecycle logic.
`scripts/stack-update-check.sh` and `scripts/stack-upgrade.sh` remain the
*clone*-level operations (they fast-forward the shared git checkout) and are
documented as such; the *project*-level update is `ainative update`. There is
no second project updater.

## Rejected alternatives

**Add `uninstall.py` beside `install.py`.** Two programs would have had to
agree, forever, on what the other wrote — with no shared record. That is how
the current state arose.

**Infer ownership at uninstall time from the distribution's file list.** A file
that matches the distribution is safe to remove, but a file the user edited
looks identical to a file from a different stack version. Without a recorded
install-time digest the two are indistinguishable, and the failure mode is
deleting the user's edit.

**Use `git clean` / `git checkout .` to uninstall or update.** It is the obvious
shortcut and it is prohibited outright: both operate on the user's whole working
tree, not on what the stack owns, and both would destroy unrelated uncommitted
work. Ownership manifest only.

**Make `active_profile = verified` grant Verified authority.** This would have
let an installer manufacture trust. Rejected under ADR-0004 and ADR-0006.

**Delete Verified state on downgrade.** A profile switch is a distribution
operation. Making it destroy an audit trail would mean a reversible-looking
command is irreversible in fact.

**Auto-apply updates.** The stack modifies the instructions an agent obeys.
Changing those without the user asking, possibly mid-session, is not an
update — it is an unrequested change of behaviour.

**A plugin architecture for update sources.** `UpdateProvider` is one small
interface with two implementations (a release source, and a local directory used
by the tests). A registry, discovery and entry points would be a product this
work is not.

## Consequences

- Uninstall and update become possible at all, because ownership is recorded
  rather than inferred.
- Every user-visible mutation gains `--dry-run`, and every confirmation gains
  `--yes`, so the CLI is usable from CI without a TTY.
- Existing installations have no lifecycle state. They are detected as
  `LEGACY_INSTALL` and adopted conservatively. A file is adopted as
  `MANAGED_IMMUTABLE`, with `created_by_ainative = true`, only when its digest
  matches a file the distribution currently ships — that is the proof an earlier
  version of the stack wrote it. A file that sits where a managed file goes but
  holds different bytes is adopted as `MANAGED_MUTABLE` with
  `created_by_ainative = false`, and that flag is what the planner reads: such a
  file is never replaced and never removed, by any operation, `--purge`
  included. Adoption makes a file *trackable*; it never makes it *ours*.

  Recording the on-disk digest alone is not enough, and the first
  implementation that did only that let the very next install overwrite a
  customised `AGENTS.md` (EMP-LC-007): the file compared `UNCHANGED` against its
  own adopted digest, so the replace path opened.
- `install.py`'s unconditional prune is a behaviour change: it now prunes only
  unchanged managed files. A user who edited a shipped skill keeps the edit.
- The lifecycle state schema, the stack release version and the Work Plane
  runtime version are three independent numbers and are compared with SemVer
  rules, never as strings.
- The lifecycle layer adds no third-party dependency: `argparse`, `json`,
  `pathlib`, `hashlib`, `urllib`, `tempfile`, `shutil`, `zipfile`.
