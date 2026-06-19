#!/usr/bin/env bash
# run_hook.sh — PostToolUse AI_SUMMARY Generator
# Wrapper universel pour Claude Code / Codex PostToolUse hook.
# Lit stdin une fois, trouve un Python, délègue à update_on_edit.py.

INPUT=$(cat)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Chemin vers le script Python de AI Native Dev Stack
UPDATE_SCRIPT="$STACK_ROOT/tools/ai_docs/update_on_edit.py"
PYTHON_BIN=""

# Trouver un Python disponible
for py in python3 python python3.11 python3.10 python3.9 python3.8; do
    if command -v $py &>/dev/null; then
        PYTHON_BIN=$py
        break
    fi
done

if [ -n "$PYTHON_BIN" ] && [ -f "$UPDATE_SCRIPT" ]; then
    echo "$INPUT" | PYTHONIOENCODING=utf-8 "$PYTHON_BIN" "$UPDATE_SCRIPT" 2>&1
else
    # Silent skip — ne pas bloquer l'agent
    :
fi

exit 0
