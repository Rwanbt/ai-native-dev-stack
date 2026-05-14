#!/usr/bin/env bash
# run_hook.sh — Claude Code PostToolUse hook wrapper.
# Reads stdin once, finds a working Python, delegates to update_on_edit.py.
# Always exits 0 so it never blocks Claude Code.

INPUT=$(cat)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/update_on_edit.py"

# Find a working Python interpreter (skips MS Store stubs)
CANDIDATES=(
    "/c/Users/barat/AppData/Local/Android/Sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/windows-x86_64/python3/python.exe"
    "/c/Users/barat/.lmstudio/extensions/backends/vendor/_amphibian/cpython3.11-win-x86@7/python.exe"
    "/c/Users/barat/.lmstudio/extensions/backends/vendor/_amphibian/cpython3.11-win-x86@6/python.exe"
    "/c/Users/barat/.lmstudio/extensions/backends/vendor/_amphibian/cpython3.11-win-x86@5/python.exe"
    "python3"
    "python"
)

for PY in "${CANDIDATES[@]}"; do
    if "$PY" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        echo "$INPUT" | PYTHONIOENCODING=utf-8 "$PY" "$SCRIPT" 2>&1
        exit 0
    fi
done

# No working Python found — silent skip (do not block Claude Code)
exit 0
