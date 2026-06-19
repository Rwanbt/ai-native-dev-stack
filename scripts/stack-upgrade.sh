#!/usr/bin/env bash
# stack-upgrade.sh — Pull the latest stack, non-destructively.
#
# Non-destructive guarantees:
#   - Refuses to run if your working tree has uncommitted changes (so a local
#     fork is never silently clobbered).
#   - Only ever fast-forwards (`git pull --ff-only`) — never a merge that could
#     rewrite your history.
#   - Touches ONLY the shared repo. Your personalized configs (~/.claude/CLAUDE.md,
#     Mavis agent.md, per-project config.sh) only *reference* this repo, so they
#     are never modified by an upgrade.
#   - Reports new keys in tracked *.example files instead of overwriting the
#     machine-local copies you derived from them.
#
# Usage:
#   bash scripts/stack-upgrade.sh            # show changelog, then ff-only pull
#   bash scripts/stack-upgrade.sh --dry-run  # show what would change, pull nothing
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DRY_RUN=""
[ "$1" = "--dry-run" ] && DRY_RUN="yes"

cd "$STACK_ROOT"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERROR: not a git clone."; exit 1; }

old_ver="$(cat VERSION 2>/dev/null || echo "0.0.0")"

# 1. Refuse to clobber local work.
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  Working tree has uncommitted changes — aborting to protect your edits."
  echo "    Commit/stash them first, then re-run. (Your changes are untouched.)"
  exit 1
fi

git fetch --quiet origin || { echo "OFFLINE — cannot reach origin. Nothing changed."; exit 0; }

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "origin/main")"
behind="$(git rev-list --count "HEAD..$upstream" 2>/dev/null || echo 0)"

if [ "$behind" -eq 0 ]; then
  echo "✅ Already up to date (v$old_ver)."
  exit 0
fi

new_ver="$(git show "$upstream:VERSION" 2>/dev/null | tr -d '[:space:]' || echo "$old_ver")"
echo "⬆️  Update available: v$old_ver -> v$new_ver ($behind commits)"
echo ""
echo "What's new:"
git log --no-merges --format='  - %s' "HEAD..$upstream"
echo ""

# 2. Surface new keys in *.example files (machine-local copies are never overwritten).
changed_examples="$(git diff --name-only "HEAD..$upstream" -- '*.example' 2>/dev/null || true)"
if [ -n "$changed_examples" ]; then
  echo "ℹ️  These template files changed — review them for new keys to copy into your"
  echo "    machine-local copies (config.sh, etc.). Your local copies are NOT touched:"
  echo "$changed_examples" | sed 's/^/      /'
  echo ""
fi

if [ -n "$DRY_RUN" ]; then
  echo "(dry-run — nothing pulled)"
  exit 0
fi

# 3. Fast-forward only.
if git pull --ff-only --quiet origin "${upstream#origin/}"; then
  echo "✅ Upgraded to v$(cat VERSION 2>/dev/null || echo "$new_ver")."
  echo "   Referenced configs (@AGENTS.md) pick up the new version automatically."
else
  echo "❌ Fast-forward failed (history diverged). Resolve manually:"
  echo "     cd $STACK_ROOT && git status"
  exit 1
fi
