#!/usr/bin/env bash
# run_hook.sh — Claude Code PostToolUse hook wrapper.
# Reads stdin once, finds a working Python, delegates to update_on_edit.py.
# Always exits 0 so it never blocks Claude Code.

INPUT=$(cat)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/update_on_edit.py"

# Delegate Python detection to find_python.sh (no hardcoded personal paths here)
CANDIDATES=()
DETECTED=$(bash "$SCRIPT_DIR/find_python.sh" 2>/dev/null)
[ -n "$DETECTED" ] && CANDIDATES+=("$DETECTED")
CANDIDATES+=("python3" "python" "py")

for PY in "${CANDIDATES[@]}"; do
    if "$PY" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        echo "$INPUT" | PYTHONIOENCODING=utf-8 "$PY" "$SCRIPT" 2>&1
        exit 0
    fi
done

# No working Python found — silent skip (do not block Claude Code)
exit 0
