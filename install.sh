#!/usr/bin/env bash
# install.sh — Set up the AI-Native Dev Stack in an existing project.
#
# Usage: bash install.sh [--project-root /path/to/project]
#
# What this does:
#   1. Copies scripts to tools/ai_docs/
#   2. Copies the verify-ai-docs skill to .claude/skills/
#   3. Creates config.sh from the template
#   4. Detects Python and validates it works
#   5. Generates all AI_SUMMARY.md files
#   6. Prints next steps (hook registration is manual — requires editing settings.json)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="${1:-$(pwd)}"

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
echo "[1/5] Copying scripts to tools/ai_docs/ ..."
mkdir -p "$PROJECT_ROOT/tools/ai_docs"
cp -f "$SCRIPT_DIR/tools/ai_docs/generate_ai_summary.py" "$PROJECT_ROOT/tools/ai_docs/"
cp -f "$SCRIPT_DIR/tools/ai_docs/update_on_edit.py"      "$PROJECT_ROOT/tools/ai_docs/"
cp -f "$SCRIPT_DIR/tools/ai_docs/generate_all.py"        "$PROJECT_ROOT/tools/ai_docs/"
cp -f "$SCRIPT_DIR/tools/ai_docs/run_hook.sh"            "$PROJECT_ROOT/tools/ai_docs/"
cp -f "$SCRIPT_DIR/tools/ai_docs/find_python.sh"         "$PROJECT_ROOT/tools/ai_docs/"
cp -f "$SCRIPT_DIR/tools/ai_docs/config.sh.example"      "$PROJECT_ROOT/tools/ai_docs/"
echo "   OK"

# ── Step 2: Copy skill ────────────────────────────────────────────────────────
echo "[2/5] Copying verify-ai-docs skill ..."
mkdir -p "$PROJECT_ROOT/.claude/skills/verify-ai-docs"
cp -f "$SCRIPT_DIR/skills/verify-ai-docs/SKILL.md" "$PROJECT_ROOT/.claude/skills/verify-ai-docs/"
echo "   OK"

# ── Step 3: Config ────────────────────────────────────────────────────────────
echo "[3/5] Creating config.sh ..."
CONFIG="$PROJECT_ROOT/tools/ai_docs/config.sh"
if [ -f "$CONFIG" ]; then
  echo "   SKIP — config.sh already exists (not overwriting)"
else
  cp "$SCRIPT_DIR/tools/ai_docs/config.sh.example" "$CONFIG"
  echo "   Created config.sh — edit it to set your Obsidian vault path and graphify binary"
fi

# ── Step 4: Python detection ──────────────────────────────────────────────────
echo "[4/5] Detecting Python ..."
PY=$(bash "$PROJECT_ROOT/tools/ai_docs/find_python.sh")
if [ -n "$PY" ]; then
  PY_VER=$("$PY" --version 2>&1)
  echo "   Found: $PY ($PY_VER)"
else
  echo "   WARNING: No Python found. Install Python 3.8+ and add to PATH,"
  echo "   or set PYTHON_BIN in tools/ai_docs/config.sh"
fi

# ── Step 5: Generate summaries ────────────────────────────────────────────────
if [ -n "$PY" ]; then
  echo "[5/5] Generating AI_SUMMARY.md for all tracked modules ..."
  cd "$PROJECT_ROOT"
  PYTHONIOENCODING=utf-8 "$PY" tools/ai_docs/generate_all.py
else
  echo "[5/5] SKIP — Python not found. Run manually: python tools/ai_docs/generate_all.py"
fi

# ── .gitignore ────────────────────────────────────────────────────────────────
GITIGNORE="$PROJECT_ROOT/.gitignore"
if ! grep -q "config.sh" "$GITIGNORE" 2>/dev/null; then
  echo "" >> "$GITIGNORE"
  echo "# AI docs stack — machine-specific config (never commit)" >> "$GITIGNORE"
  echo "tools/ai_docs/config.sh" >> "$GITIGNORE"
  echo "   Added config.sh to .gitignore"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  INSTALL COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Edit tools/ai_docs/config.sh:"
echo "   - Set OBSIDIAN_VAULT to your vault root path"
echo "   - Set OBSIDIAN_PROJECT_DIR to this project's vault subfolder"
echo "   - Set GRAPHIFY_BIN if graphify isn't in PATH"
echo "   - Set CLAUDE_MEMORY_KEY (run: ls ~/.claude/projects/)"
echo ""
echo "2. Register the PostToolUse hook in .claude/settings.json:"
echo "   See templates/settings_hook_example.json for the exact JSON to add."
echo "   Replace /ABSOLUTE/PATH/TO/... with: $PROJECT_ROOT"
echo ""
echo "3. Write AI_CONTEXT.md for each source module:"
echo "   Use templates/AI_CONTEXT_template.md as your starting point."
echo ""
echo "4. Verify the full stack:"
echo "   In Claude Code: /verify-ai-docs"
echo ""
