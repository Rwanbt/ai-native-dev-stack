# Updating the stack — constant, non-destructive optimization

How the AI-Native Dev Stack evolves without ever destroying a user's
personalization. Modelled on Garry Tan's **gstack**: the shared layer is a git
clone you `pull`; your personal layer only *references* it.

## The one principle: reference, don't copy

Every problem with "shared config that users customize" comes from **copying**
the shared content into a personal file. The copy forks on the first edit, and
the next update either clobbers the user's edits or is silently ignored.

The stack avoids this entirely:

| Layer | Owner | How a user consumes it | What an update does |
|---|---|---|---|
| **Shared method** (`AGENTS.md`, skills, hooks, anti-debt) | the repo | references it (`@AGENTS.md`), links it (`setup-agents.sh`) | `git pull` updates it in place — references see the new version instantly |
| **Personal** (`~/.claude/CLAUDE.md`, Mavis `agent.md`) | the user | owns the file; it *includes* the shared method | **nothing** — the updater never opens these files |
| **Machine-local** (`config.sh`) | the user | copies from `*.example`, git-ignored | the updater reports new `*.example` keys; never overwrites the copy |

Because personalization lives in files the updater never touches, two users with
completely different `CLAUDE.md` files both get the same method update from one
`git pull`, and neither loses a single customization.

## Detecting updates (simple for every user)

A read-only check — it fetches and compares, never modifies anything:

```bash
bash scripts/stack-update-check.sh
# → UP_TO_DATE 1.0.0
# → UPGRADE_AVAILABLE 1.0.0 -> 1.1.0 (4 commits)
# → OFFLINE | NOT_A_CLONE
```

Wire it wherever you want a passive notice:
- **SessionStart hook** — print the one-liner at the top of each session.
- **`/stack-upgrade` skill** — runs it as Step 1 and offers to upgrade.

Version source of truth: the `VERSION` file (semver) + the `stack-version` header
in `AGENTS.md`. The `CHANGELOG.md` describes each change.

## Applying updates (non-destructive by construction)

```bash
bash scripts/stack-upgrade.sh          # or the /stack-upgrade skill
```

Guarantees:
1. **Aborts on a dirty working tree** — a local fork is never silently clobbered.
2. **Fast-forward only** (`git pull --ff-only`) — never a history-rewriting merge.
3. **Touches only the shared repo** — referenced configs pick up the new version
   automatically; no personal file is opened.
4. **Reports changed `*.example` templates** instead of overwriting your derived
   machine-local copies.

## When content MUST be inlined: the managed-block convention

A few files can't be pure references — e.g. a project-root `AGENTS.md` that a
team wants to extend, or a `CLAUDE.md` that prefers inlining over `@include`.
For those, wrap the stack-managed region in markers and edit only outside them:

```markdown
<!-- STACK:BEGIN v1.0.0 — managed by ai-native-dev-stack, do not edit inside -->
... canonical content, replaced wholesale on update ...
<!-- STACK:END -->

## My project-specific additions   ← outside the block, never touched by updates
- ...
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

**Prefer the `@AGENTS.md` reference** wherever the tool supports it (Claude Code,
Cursor, Codex) — it needs no markers and no sync at all.

## For maintainers: cutting a release

1. Land changes via PRs (squash merge, CI green).
2. Bump `VERSION` (semver) and the `stack-version` header in `AGENTS.md`.
3. Move `CHANGELOG.md` `[Unreleased]` items under `## [x.y.z] - YYYY-MM-DD`.
4. Tag: `git tag vX.Y.Z && git push --tags`.

Users then see `UPGRADE_AVAILABLE` and upgrade with one command — no personal
config is ever at risk.
