#!/usr/bin/env bash
# setup-agents.sh — Link the stack's portable agents into each AI agent's root.
#
# The anti-debt agent must be linked as a WHOLE directory (its scanners
# reference ../tools and ../kg relatively, so linking skills/ alone breaks
# resolution). Path.resolve() follows links/junctions, so a single link works.
#
# Idempotent: skips a target that already points at the right place.
# Cross-platform: ln -s on Linux/macOS, a directory junction on Windows
# (junctions need no admin rights and Path.resolve() follows them).
#
# Usage:
#   bash scripts/setup-agents.sh            # link into every detected agent root
#   bash scripts/setup-agents.sh --dry-run  # show what would happen, do nothing
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ANTI_DEBT_SRC="$STACK_ROOT/stack/agents/anti-debt"
DRY_RUN=""
[ "$1" = "--dry-run" ] && DRY_RUN="yes"

# Agent roots: "<label>:<dir where the agent looks for its agents/skills>"
AGENT_ROOTS=(
  "Claude Code:$HOME/.claude/skills"
  "MiniMax (Mavis):$HOME/.mavis/agents"
)

is_windows() { case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac; }

# Create a directory link at $2 pointing to $1, OS-appropriate.
make_link() {
  local target="$1" link="$2"
  if is_windows; then
    # Translate /c/Users/... → C:\Users\... for PowerShell, use a junction.
    local win_link win_target
    win_link="$(cygpath -w "$link" 2>/dev/null || echo "$link")"
    win_target="$(cygpath -w "$target" 2>/dev/null || echo "$target")"
    powershell.exe -NoProfile -Command \
      "New-Item -ItemType Junction -Path '$win_link' -Target '$win_target' | Out-Null" 2>/dev/null
  else
    ln -s "$target" "$link"
  fi
}

# Resolve a link target to an absolute path (portable readlink -f).
resolve() { cd "$1" 2>/dev/null && pwd -P; }

echo ""
echo "Stack agents setup"
echo "=================="
echo "Source: $ANTI_DEBT_SRC"
[ -n "$DRY_RUN" ] && echo "(dry-run — no changes)"
echo ""

if [ ! -d "$ANTI_DEBT_SRC" ]; then
  echo "ERROR: anti-debt source not found at $ANTI_DEBT_SRC"
  exit 1
fi

linked=0
for entry in "${AGENT_ROOTS[@]}"; do
  label="${entry%%:*}"
  root="${entry#*:}"
  link="$root/anti-debt"

  if [ ! -d "$root" ]; then
    echo "  -  $label: agent root not present ($root) — skipping"
    continue
  fi

  if [ -e "$link" ] || [ -L "$link" ]; then
    current="$(resolve "$link" 2>/dev/null || true)"
    expected="$(resolve "$ANTI_DEBT_SRC")"
    if [ "$current" = "$expected" ]; then
      echo "  ✅ $label: already linked correctly"
    else
      echo "  ⚠️  $label: $link exists but points elsewhere ($current) — leaving untouched"
    fi
    continue
  fi

  if [ -n "$DRY_RUN" ]; then
    echo "  →  $label: would link $link → $ANTI_DEBT_SRC"
  else
    make_link "$ANTI_DEBT_SRC" "$link"
    if [ -e "$link" ]; then
      echo "  ✅ $label: linked $link → anti-debt"
      linked=$((linked + 1))
    else
      echo "  ❌ $label: link failed — see PORTABILITY.md for the manual command"
    fi
  fi
done

echo ""
echo "Done. ${linked} new link(s)."
echo "Activate per agent (load the method + run the agent): see PORTABILITY.md"
