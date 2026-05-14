#!/usr/bin/env bash
# install.sh — Set up the AI-Native Dev Stack in an existing project.
#
# Usage:
#   bash install.sh [--project-root /path/to/project] [--with-gstack] [--skip-gstack]
#
# What this does:
#   1. Copies scripts to tools/ai_docs/
#   2. Copies the verify-ai-docs skill to .claude/skills/
#   3. Installs gstack (global Claude Code skills by Garry Tan / YC) — optional
#   4. Creates config.sh from the template
#   5. Detects Python and validates it works
#   6. Generates all AI_SUMMARY.md files
#   7. Adds config.sh to .gitignore
#   8. Prints next steps

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(pwd)"
INSTALL_GSTACK=""   # "", "yes", "no"

# ── Argument parsing ──────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --project-root=*) PROJECT_ROOT="${arg#*=}" ;;
    --project-root)   shift; PROJECT_ROOT="$1" ;;
    --with-gstack)    INSTALL_GSTACK="yes" ;;
    --skip-gstack)    INSTALL_GSTACK="no"  ;;
  esac
done

echo ""
echo "AI-Native Dev Stack — Installer"
echo "================================"
echo "Source:  $SCRIPT_DIR"
echo "Project: $PROJECT_ROOT"
echo ""

# Verify it's a git repo
if [ ! -d "$PROJECT_ROOT/.git" ]; then
  echo "ERROR: $PROJECT_ROOT is not a git repository."
  exit 1
fi

# ── Step 1: Copy scripts ──────────────────────────────────────────────────────
echo "[1/6] Copying scripts to tools/ai_docs/ ..."
mkdir -p "$PROJECT_ROOT/tools/ai_docs"
for F in \
  generate_ai_summary.py \
  update_on_edit.py \
  generate_all.py \
  assemble_context.py \
  run_hook.sh \
  find_python.sh \
  config.sh.example; do
  [ -f "$SCRIPT_DIR/tools/ai_docs/$F" ] && cp -f "$SCRIPT_DIR/tools/ai_docs/$F" "$PROJECT_ROOT/tools/ai_docs/"
done
echo "   OK (6 scripts + assembler)"

# ── Step 2: Copy skill ────────────────────────────────────────────────────────
echo "[2/6] Copying verify-ai-docs skill ..."
mkdir -p "$PROJECT_ROOT/.claude/skills/verify-ai-docs"
cp -f "$SCRIPT_DIR/skills/verify-ai-docs/SKILL.md" "$PROJECT_ROOT/.claude/skills/verify-ai-docs/"
echo "   OK"

# ── Step 3: gstack — Global engineering skills (optional) ────────────────────
echo ""
echo "[3/6] gstack — Global Claude Code skills by Garry Tan / YC"
echo "   Provides: /investigate /review /qa /ship /plan-eng-review /office-hours ..."
echo "   Installs to: ~/.claude/skills/gstack/ (available across ALL your projects)"
echo "   Source: https://github.com/garrytan/gstack"
echo ""

GSTACK_DIR="$HOME/.claude/skills/gstack"

if [ -d "$GSTACK_DIR" ]; then
  echo "   ALREADY INSTALLED at $GSTACK_DIR — skipping"
  INSTALL_GSTACK="no"
fi

if [ "$INSTALL_GSTACK" = "" ]; then
  # Interactive prompt (with 15s timeout defaulting to yes)
  printf "   Install gstack? [Y/n] "
  if read -r -t 15 REPLY 2>/dev/null; then
    case "$REPLY" in
      [nN]*) INSTALL_GSTACK="no" ;;
      *)     INSTALL_GSTACK="yes" ;;
    esac
  else
    echo ""
    echo "   (no input — defaulting to Y)"
    INSTALL_GSTACK="yes"
  fi
fi

if [ "$INSTALL_GSTACK" = "yes" ]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "   ERROR: git not found — cannot install gstack. Install git and retry."
    INSTALL_GSTACK="no"
  else
    echo "   Cloning gstack ..."
    git clone --single-branch --depth 1 \
      https://github.com/garrytan/gstack.git \
      "$GSTACK_DIR" 2>&1 | sed 's/^/   /'

    if [ -f "$GSTACK_DIR/setup" ]; then
      echo "   Running setup ..."
      (cd "$GSTACK_DIR" && ./setup) 2>&1 | sed 's/^/   /'
    fi
    echo "   gstack installed OK"
    echo ""
    echo "   Add this section to your CLAUDE.md (or global ~/.claude/CLAUDE.md):"
    echo ""
    cat << 'GSTACK_CLAUDE_SNIPPET'
   ## gstack skills
   When working with Claude Code, the following gstack skills are available:
   /investigate, /review, /qa, /ship, /plan-eng-review, /plan-ceo-review,
   /office-hours, /autoplan, /benchmark, /canary, /land-and-deploy,
   /retro, /cso, /document-release, /learn, /browse, /careful, /guard,
   /context-save, /context-restore, /gstack-upgrade, /health, /codex
   For web browsing: always use /browse — never use mcp__claude-in-chrome__* tools.
GSTACK_CLAUDE_SNIPPET
  fi
fi

[ "$INSTALL_GSTACK" = "no" ] && echo "   Skipped."
echo ""

# ── Step 4: Config ────────────────────────────────────────────────────────────
echo "[4/6] Creating config.sh ..."
CONFIG="$PROJECT_ROOT/tools/ai_docs/config.sh"
if [ -f "$CONFIG" ]; then
  echo "   SKIP — config.sh already exists (not overwriting)"
else
  cp "$SCRIPT_DIR/tools/ai_docs/config.sh.example" "$CONFIG"
  echo "   Created config.sh — edit it to set your Obsidian vault path and graphify binary"
fi

# ── Step 5: Python detection ──────────────────────────────────────────────────
echo "[5/6] Detecting Python ..."
PY=$(bash "$PROJECT_ROOT/tools/ai_docs/find_python.sh" 2>/dev/null || true)
if [ -n "$PY" ]; then
  PY_VER=$("$PY" --version 2>&1)
  echo "   Found: $PY ($PY_VER)"
else
  echo "   WARNING: No Python 3.8+ found."
  echo "   Install Python and add to PATH, or set PYTHON_BIN in tools/ai_docs/config.sh"
fi

# ── Step 6: Generate summaries ────────────────────────────────────────────────
if [ -n "$PY" ]; then
  CTX_COUNT=$(find "$PROJECT_ROOT" -name "AI_CONTEXT.md" \
    -not -path "*/.git/*" -not -path "*/node_modules/*" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$CTX_COUNT" -gt 0 ]; then
    echo "[6/6] Generating AI_SUMMARY.md for $CTX_COUNT tracked module(s) ..."
    cd "$PROJECT_ROOT"
    PYTHONIOENCODING=utf-8 "$PY" tools/ai_docs/generate_all.py
  else
    echo "[6/6] SKIP — no AI_CONTEXT.md files found yet."
    echo "   Create one per module using templates/AI_CONTEXT_template.md, then run:"
    echo "   python tools/ai_docs/generate_all.py"
  fi
else
  echo "[6/6] SKIP — Python not found."
fi

# ── .gitignore ────────────────────────────────────────────────────────────────
GITIGNORE="$PROJECT_ROOT/.gitignore"
if ! grep -q "tools/ai_docs/config.sh" "$GITIGNORE" 2>/dev/null; then
  echo "" >> "$GITIGNORE"
  echo "# AI docs stack — machine-specific config (never commit)" >> "$GITIGNORE"
  echo "tools/ai_docs/config.sh" >> "$GITIGNORE"
  echo "   Added config.sh to .gitignore"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  INSTALL COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Edit tools/ai_docs/config.sh:"
echo "   - OBSIDIAN_VAULT    → your Obsidian vault root path"
echo "   - OBSIDIAN_PROJECT_DIR → this project's vault subfolder"
echo "   - GRAPHIFY_BIN      → if graphify isn't in PATH"
echo "   - CLAUDE_MEMORY_KEY → run: ls ~/.claude/projects/"
echo ""
echo "2. Register the PostToolUse hook in .claude/settings.json:"
echo "   See templates/settings_hook_example.json for the JSON."
echo "   Replace ABSOLUTE_PATH with: $PROJECT_ROOT"
echo ""
echo "3. Write AI_CONTEXT.md for each source module:"
echo "   Template: templates/AI_CONTEXT_template.md"
echo ""
echo "4. Verify the full stack:"
echo "   In Claude Code: /verify-ai-docs"
echo ""
if [ "$INSTALL_GSTACK" = "yes" ]; then
  echo "5. Add the gstack skills block to your CLAUDE.md (see above)."
  echo ""
fi
