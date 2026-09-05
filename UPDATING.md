# Updating the stack

There are two things called "the stack", and they update differently. Knowing
which one you have takes ten seconds and saves an afternoon.

| You consume the stack by… | You update with… | What moves |
|---|---|---|
| **reference** — `@AGENTS.md`, symlinked skills, a clone you point your tools at | `bash scripts/stack-upgrade.sh` | the shared git clone |
| **install** — you ran `ainative init` (or the old `install.py`) in a project | `ainative update` | that project's installed files |

Most people who followed the README end up with both: a clone they reference
globally, and one or more projects they installed into. Update the clone, then
update each project.

The full model — ownership, transactions, rollback, security boundaries — is in
[docs/DISTRIBUTION-LIFECYCLE.md](docs/DISTRIBUTION-LIFECYCLE.md), decided in
[ADR-0009](docs/adr/0009-distribution-profiles-and-lifecycle-ownership.md).

---

## Updating a project — `ainative update`

```bash
ainative update check      # is there anything newer?
ainative update --dry-run  # exactly what would change
ainative update            # apply it
ainative update rollback   # undo it
```

### What it guarantees

1. **Your edits survive.** Every managed file carries the SHA-256 it had when
   the stack wrote it. A file whose bytes no longer match is never overwritten:
   it keeps your content and the new version lands beside it as `<name>.new`,
   reported as a conflict. Nothing is merged — a deterministic merge of
   arbitrary content is not available, and an LLM merge has no place in a core
   that must produce the same result twice.

2. **It is a transaction.** Backup, apply, verify, then commit the install state
   *last*. An interruption leaves the old valid state on disk plus a journal
   entry; `ainative repair` completes the rollback from the recorded backup.
   There is no half-updated project.

3. **Your data is untouched.** `.ai-native/trust/`, `.ai-native/work/` and
   `.ai-native/runs/` — the trust anchor, Work Contracts, revisions, approvals
   and run evidence — are `USER_DATA`. No update rewrites them. Historical Work
   revisions and Run evidence are never rewritten to make an update succeed.

4. **Your `.gitignore` is not rewritten.** The stack owns one delimited region
   inside it and touches nothing else.

5. **It never runs git.** No `git clean`, no `git checkout .`, no `git restore
   .`, no commit, no push. Those operate on your whole working tree rather than
   on what the stack owns.

### Detection, and the line it does not cross

The stack may **detect** a new release automatically. It never **applies** one
automatically — it modifies the instructions your agent obeys, and changing
those without being asked is not an update.

```
AI Native 1.4.0 is available.
Current: 1.3.2
Run `ainative update`
```

Checks are cached (24 h by default) and bounded by a 5-second timeout.
`OFFLINE` and `CHECK_FAILED` are outcomes, not errors — nothing blocks.

```json
"update_preferences": {
  "enabled": true, "auto_check": true, "check_interval": 86400, "channel": "stable"
}
```

`AINATIVE_NO_UPDATE_CHECK=1` turns off every network check, for CI and offline
machines.

**`ainative verify`, `converge`, `trust` and `work` never trigger a check.** A
command that produces a verdict must not depend on what a remote server said.
They may print an already-cached notice and nothing more.

### Integrity — what SHA-256 does and does not buy

The release archive's digest is verified before a single byte is written, and
every entry name inside it is validated by the same containment rule that guards
every other destination (`../../etc/cron.d/x` is refused before extraction, as
are archives over the entry-count and expanded-size limits).

That protects you against a **corrupted, truncated or substituted archive on the
wire**. It does **not** protect you against a **compromised release source** —
an attacker who controls the source controls both the archive and the digest it
publishes. Release signing is not implemented and is not claimed.

### Rollback, and its exact scope

```bash
ainative update rollback --dry-run
ainative update rollback
```

Restores the **project's installed assets** from the update transaction's
backup, while that transaction is still retained (the last 5). It cannot restore
a Python package installed elsewhere on your machine and does not pretend to —
reinstall that with your package manager.

---

## Updating the clone — `scripts/stack-upgrade.sh`

```bash
bash scripts/stack-update-check.sh
# → UP_TO_DATE 2.0.0
# → UPGRADE_AVAILABLE 2.0.0 -> 2.1.0 (4 commits)
# → OFFLINE | NOT_A_CLONE

bash scripts/stack-upgrade.sh            # show the changelog, then ff-only pull
bash scripts/stack-upgrade.sh --dry-run
```

Guarantees, unchanged:

1. **Aborts on a dirty working tree** — a local fork is never silently clobbered.
2. **Fast-forward only** (`git pull --ff-only`) — never a history-rewriting merge.
3. **Touches only the shared repo** — referenced configs pick up the new version
   automatically; no personal file is opened.
4. **Reports changed `*.example` templates** instead of overwriting the
   machine-local copies you derived from them.

This does not update any project you installed into. It cannot: it reads no
install state, no ownership record and no digest, so it cannot tell your edit
from a shipped file. That is precisely why `ainative update` exists.

---

## The one principle: reference, don't copy

Every problem with "shared config that users customize" comes from **copying**
the shared content into a personal file. The copy forks on the first edit, and
the next update either clobbers the user's edits or is silently ignored.

| Layer | Owner | How a user consumes it | What an update does |
|---|---|---|---|
| **Shared method** (`AGENTS.md`, skills, hooks, anti-debt) | the repo | references it (`@AGENTS.md`), links it (`setup-agents.sh`) | `git pull` updates it in place — references see the new version instantly |
| **Personal** (`~/.claude/CLAUDE.md`, Mavis `agent.md`) | the user | owns the file; it *includes* the shared method | **nothing** — the updater never opens these files |
| **Machine-local** (`config.sh`) | the user | copies from `*.example`, git-ignored | classified `USER_DATA`; never overwritten, never removed |
| **Installed into a project** (`tools/ai_docs/`, skills, `AGENTS.md`) | the stack, with recorded ownership | `ainative init` | `ainative update`, per-file, by digest |

Where a copy is unavoidable, ownership is recorded rather than assumed. That is
the whole of ADR-0009.

---

## When content MUST be inlined: the managed-block convention

A few files can't be pure references — e.g. a project-root `AGENTS.md` that a
team wants to extend, or a `CLAUDE.md` that prefers inlining over `@include`.
For those, wrap the stack-managed region in markers and edit only outside them:

```markdown
<!-- STACK:BEGIN v2.0.0 — managed by ai-native-dev-stack, do not edit inside -->
... canonical content, replaced wholesale on update ...
<!-- STACK:END -->

## My project-specific additions   ← outside the block, never touched by updates
```

Regenerate the block from the canonical source with:

```bash
python3 scripts/sync_inlined_method.py <target-file>        # refresh the block
python3 scripts/sync_inlined_method.py <target-file> --check # CI/pre-commit: fail if stale
```

It replaces only the bytes between `STACK:BEGIN`/`STACK:END` (backing up the
target first); everything outside survives. This is the path for tools without
an import directive — e.g. **MiniMax/Mavis**, whose `agent.md` has no `@file`
include, so the method is inlined in a managed block and re-synced on update.

The same convention, with the same exact-inverse guarantee, is what the
lifecycle layer uses for `.gitignore` — see `EXTERNAL_CONFIG` in
[docs/DISTRIBUTION-LIFECYCLE.md](docs/DISTRIBUTION-LIFECYCLE.md).

**Prefer the `@AGENTS.md` reference** wherever the tool supports it (Claude Code,
Cursor, Codex) — it needs no markers and no sync at all.

---

## Migrating from the pre-lifecycle installer

If you installed before the lifecycle existed, your project has real managed
files and no install state. Nothing is broken and nothing needs migrating by
hand — the next `ainative init` adopts it:

```
Existing AI Native installation detected (24 files).
Adopting managed components without overwriting user files.
```

Adoption is conservative in one direction only. A file whose digest matches what
the distribution ships is adopted as managed. A file that sits where a managed
file goes but holds different bytes is *tracked* but never replaced and never
removed — by an update, an uninstall, or `--purge`. Adoption can never make the
uninstaller delete something the stack did not write.

The old flags still work: `python install.py --project-root PATH --skip-gstack`
does what it always did, now through the lifecycle manager.

---

## For maintainers: cutting a release

1. Land changes via PRs (squash merge, CI green).
2. Bump `VERSION` (semver) and the `stack-version` header in `AGENTS.md`.
3. Move `CHANGELOG.md` `[Unreleased]` items under `## [x.y.z] - YYYY-MM-DD`.
4. Tag: `git tag vX.Y.Z && git push --tags`.
5. Publish a release with a `.zip` asset. `ainative update check` resolves the
   latest release from that source; the archive's SHA-256 is verified before any
   file is written.

Users then see `UPDATE_AVAILABLE` and update with one command — no personal
config, and no edit of theirs, is ever at risk.
