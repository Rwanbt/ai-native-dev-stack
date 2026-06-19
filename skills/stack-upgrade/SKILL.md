---
name: stack-upgrade
description: |
  Check for and apply AI-Native Dev Stack updates, non-destructively.
  Detects whether the stack repo is behind upstream, shows what changed, and
  fast-forwards the shared clone — without ever touching your personalized
  configs (CLAUDE.md, Mavis agent.md, config.sh).
  Use when: "upgrade the stack", "update ai-native-dev-stack", "is the stack
  up to date?", "get the latest rules/method".
  Proactively suggest at the start of a session if an update is available.
origin: generic
---

# /stack-upgrade — Non-destructive stack update

The stack follows the gstack model: **reference, don't copy**. The shared layer
is this git repo; your personal layer only *references* it (`@AGENTS.md`). So an
update is just a `git pull` on the shared clone — your personalization is never
overwritten. See [UPDATING.md](../../UPDATING.md) for the full model.

Use real tool calls. Never assume the result of a step.

## Step 1 — Detect

Run the read-only check (fetches and compares; changes nothing):

```bash
bash scripts/stack-update-check.sh
```

Interpret the single-line output:
- `UP_TO_DATE <version>` → tell the user they're current. **Stop.**
- `UPGRADE_AVAILABLE <old> -> <new> (<N> commits)` → continue to Step 2.
- `OFFLINE` → no network/remote; tell the user and stop.
- `NOT_A_CLONE` → the stack isn't a git clone here; point to PORTABILITY.md.

## Step 2 — Ask the user

The stack version `<new>` is available (you're on `<old>`). Use AskUserQuestion:
- Question: "AI-Native Dev Stack v{new} is available (you're on v{old}). Upgrade now?"
- Options: ["Yes, upgrade now", "Show me what changed first", "Not now"]

**"Show me what changed first":** run `bash scripts/stack-upgrade.sh --dry-run`
(shows the changelog + any changed `*.example` templates, pulls nothing), then
ask again.

**"Not now":** stop, do not nag again this session.

## Step 3 — Upgrade (non-destructive)

```bash
bash scripts/stack-upgrade.sh
```

The script:
1. **Aborts if your working tree is dirty** — your local edits are protected.
2. **Fast-forwards only** (`git pull --ff-only`) — never a history-rewriting merge.
3. **Touches only the shared repo** — referenced configs (`@AGENTS.md`) pick up
   the new version automatically; nothing personal is modified.
4. **Reports new keys in `*.example` files** so you can copy them into your
   machine-local copies (`config.sh`) yourself — it never overwrites them.

## Step 4 — Report

State the new version and summarize what changed (from the changelog the script
printed). If `*.example` files changed, remind the user to review them for new
keys. Do not edit any machine-local file on the user's behalf without asking.
