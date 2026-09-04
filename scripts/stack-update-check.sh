#!/usr/bin/env bash
# stack-update-check.sh — is the stack *clone* behind its upstream?
#
# SCOPE. This is the clone-level check: it asks whether this git checkout of the
# stack has commits waiting upstream. It says nothing about the files installed
# into any project.
#
#   this script          the shared git clone      `git fetch` + compare
#   ainative update      one project's install     recorded ownership, digests,
#                                                  transactional apply
#
# For a project, use `ainative update check` — it is the single authority for
# project-level updates (ADR-0009 §7). Running this one is still correct when
# you consume the stack by referencing the clone (@AGENTS.md, symlinked skills)
# rather than by installing into the project.
#
# READ-ONLY by design: it fetches and compares, never modifies your working
# tree, never merges, never touches any personalized config. Safe to run from a
# SessionStart hook on every session.
#
# Output (one line, machine-parseable):
#   UP_TO_DATE <version>
#   UPGRADE_AVAILABLE <local-version> -> <remote-version> (<N> commits)
#   OFFLINE                     # fetch failed (no network / no remote)
#   NOT_A_CLONE                 # not run from inside the stack git repo
#
# Usage: bash scripts/stack-update-check.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

git -C "$STACK_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "NOT_A_CLONE"; exit 0; }

local_ver="$(cat "$STACK_ROOT/VERSION" 2>/dev/null || echo "0.0.0")"

# Fetch quietly; if it fails (offline / no remote), report and stop — never block.
if ! git -C "$STACK_ROOT" fetch --quiet origin 2>/dev/null; then
  echo "OFFLINE"
  exit 0
fi

# Compare the current branch against its upstream (fallback: origin/main).
upstream="$(git -C "$STACK_ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "origin/main")"
behind="$(git -C "$STACK_ROOT" rev-list --count "HEAD..$upstream" 2>/dev/null || echo 0)"

if [ "$behind" -eq 0 ]; then
  echo "UP_TO_DATE $local_ver"
  exit 0
fi

remote_ver="$(git -C "$STACK_ROOT" show "$upstream:VERSION" 2>/dev/null | tr -d '[:space:]' || echo "$local_ver")"
echo "UPGRADE_AVAILABLE $local_ver -> $remote_ver ($behind commits)"
