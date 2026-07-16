#!/usr/bin/env bash
# validate-commit.sh — Conventional Commits PreToolUse hook
# Reads hook input from stdin (Claude Code protocol), extracts the commit
# message via extract_commit_msg.py, validates the first line, emits JSON.
#
# Contract: ALWAYS emits a JSON object on stdout (even on PASS).
# Exit code is always 0 — the hook only influences behavior through
# permissionDecision, never through exit code.
#
# Rules enforced (see SKILL.md for the full reference):
#   - Subject (the part after the colon): ≤ 72 chars
#   - Full first line: ≤ 100 chars (GitHub UI truncation point)
#   - First line regex: ^(type)(\(scope\))?!?: .{1,72}$
#   - WARN conditions (BREAKING CHANGE without `!`, full line > 100) are
#     surfaced as `ask` with a [warn] prefix because Claude Code does not
#     reliably display permissionDecisionReason when decision is `allow`.

set -e

# ── Locate a working Python (python3 on Linux/WSL, python on Windows) ─────────
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
if [ -z "$PY" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"validate-commit.sh: no python on PATH — skipping validation"}}\n'
  exit 0
fi

# ── Locate this script's directory (so extract_commit_msg.py is found) ────────
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACTOR="$SELF_DIR/extract_commit_msg.py"
if [ ! -f "$EXTRACTOR" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"validate-commit.sh: extract_commit_msg.py missing — skipping validation"}}\n'
  exit 0
fi

# ── Helpers (defined first — bash has no hoisting) ────────────────────────────
emit() {
  "$PY" -c "
import sys, json
print(json.dumps({
  'hookSpecificOutput': {
    'hookEventName': 'PreToolUse',
    'permissionDecision': sys.argv[1],
    'permissionDecisionReason': sys.argv[2],
  }
}))
" "$1" "$2"
}

# ── Read hook input ───────────────────────────────────────────────────────────
INPUT=$(cat)

COMMAND=$(printf '%s' "$INPUT" \
  | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" \
  2>/dev/null || echo "")

if [ -z "$COMMAND" ]; then
  emit allow ""
  exit 0
fi

# ── Only act on git commit commands ───────────────────────────────────────────
# Match "git commit" anywhere in the command (also catches "git -C /path commit")
if ! printf '%s' "$COMMAND" | grep -qE '^[[:space:]]*git[[:space:]].*\bcommit\b'; then
  emit allow ""
  exit 0
fi

# Respect explicit override
if printf '%s' "$COMMAND" | grep -q -- '--no-verify'; then
  emit allow "user override (--no-verify)"
  exit 0
fi

# ── Extract the commit message via the dedicated Python helper ────────────────
MSG=$(printf '%s' "$COMMAND" | "$PY" "$EXTRACTOR" extract 2>/dev/null || echo "")
MSG=$(printf '%s' "$MSG" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

if [ -z "$MSG" ]; then
  emit ask "No commit message found. Conventional Commits requires: <type>[(<scope>)][!]: <subject>"
  exit 0
fi

FIRST_LINE=$(printf '%s' "$MSG" | head -1)
FIRST_LEN=${#FIRST_LINE}

# ── Validate first line against Conventional Commits 1.0 ──────────────────────
RE='^(feat|fix|refactor|perf|docs|test|chore|build|ci|style|revert)(\([a-z0-9-]{1,20}\))?!?: .{1,72}$'

if printf '%s' "$FIRST_LINE" | grep -qE "$RE"; then
  # PASS — but check soft warnings
  if [ "$FIRST_LEN" -gt 100 ]; then
    emit ask "[warn] First line is ${FIRST_LEN} chars (GitHub truncates at 100). Consider tightening.

First line: $FIRST_LINE"
    exit 0
  fi
  # Trailing period is a CC convention violation (subject-full-stop)
  if printf '%s' "$FIRST_LINE" | grep -qE '\.$'; then
    emit ask "[warn] Subject ends with a period — remove it.

First line: $FIRST_LINE"
    exit 0
  fi
  if printf '%s' "$MSG" | grep -qE '^BREAKING CHANGE:' \
     && ! printf '%s' "$FIRST_LINE" | grep -qE '!'; then
    emit ask "[warn] Footer has 'BREAKING CHANGE:' but type lacks '!' suffix. Consider: ${FIRST_LINE%:*}!: ..."
    exit 0
  fi
  emit allow ""
  exit 0
fi

# ── FAIL — build hint via Python helper ───────────────────────────────────────
HINT=$("$PY" "$EXTRACTOR" hint "$FIRST_LINE" 2>/dev/null || echo "Commit message does not follow Conventional Commits 1.0. First line: $FIRST_LINE")
emit ask "$HINT"
exit 0