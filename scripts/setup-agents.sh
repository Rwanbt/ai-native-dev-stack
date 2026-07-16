#!/usr/bin/env bash
# setup-agents.sh — Link the stack's portable agents/skills into each AI agent's root.
#
# Each package is linked as a WHOLE directory: anti-debt's scanners reference
# ../tools and ../kg relatively, and commit-convention's hook resolves
# extract_commit_msg.py relative to its own bin/ — linking a subdir alone
# would break both. Path.resolve() follows links/junctions, so one link works.
#
# Idempotent: skips a target that already points at the right place, and never
# touches a target that exists but is NOT our link (e.g. a real copy placed by
# install.sh under Claude Code's .claude/skills/commit-convention/) — it is
# reported as "leaving untouched" rather than overwritten.
#
# Cross-platform: ln -s on Linux/macOS, a directory junction on Windows
# (junctions need no admin rights and Path.resolve() follows them).
#
# Usage:
#   bash scripts/setup-agents.sh            # link every package into every detected agent root
#   bash scripts/setup-agents.sh --dry-run  # show what would happen, do nothing
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DRY_RUN=""
[ "$1" = "--dry-run" ] && DRY_RUN="yes"

# Packages to link: "<link-name>:<source dir under the stack repo>"
PACKAGES=(
  "anti-debt:$STACK_ROOT/stack/agents/anti-debt"
  "commit-convention:$STACK_ROOT/skills/commit-convention"
)

# Agent roots: "<label>:<dir where the agent looks for its agents/skills>"
AGENT_ROOTS=(
  "Claude Code:$HOME/.claude/skills"
  "MiniMax (Mavis):$HOME/.mavis/agents"
  "Codex / MiniMaxCode:$HOME/.agents/skills"
  "OpenCode:$HOME/.config/opencode/skills"
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
[ -n "$DRY_RUN" ] && echo "(dry-run — no changes)"
echo ""

linked=0
for pkg in "${PACKAGES[@]}"; do
  pkg_name="${pkg%%:*}"
  pkg_src="${pkg#*:}"

  echo "Package: $pkg_name"
  echo "Source: $pkg_src"

  if [ ! -d "$pkg_src" ]; then
    echo "  ERROR: source not found — skipping this package"
    echo ""
    continue
  fi

  for entry in "${AGENT_ROOTS[@]}"; do
    label="${entry%%:*}"
    root="${entry#*:}"
    link="$root/$pkg_name"

    if [ ! -d "$root" ]; then
      echo "  -  $label: agent root not present ($root) — skipping"
      continue
    fi

    if [ -e "$link" ] || [ -L "$link" ]; then
      current="$(resolve "$link" 2>/dev/null || true)"
      expected="$(resolve "$pkg_src")"
      if [ "$current" = "$expected" ]; then
        echo "  ✅ $label: already linked correctly"
      else
        echo "  ⚠️  $label: $link exists but points elsewhere ($current) — leaving untouched"
      fi
      continue
    fi

    if [ -n "$DRY_RUN" ]; then
      echo "  →  $label: would link $link → $pkg_src"
    else
      make_link "$pkg_src" "$link"
      if [ -e "$link" ]; then
        echo "  ✅ $label: linked $link → $pkg_name"
        linked=$((linked + 1))
      else
        echo "  ❌ $label: link failed — see PORTABILITY.md for the manual command"
      fi
    fi
  done
  echo ""
done

echo "Done. ${linked} new link(s)."
echo "Activate per agent (load the method + run the agent): see PORTABILITY.md"
