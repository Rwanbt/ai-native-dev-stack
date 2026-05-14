#!/usr/bin/env bash
# find_python.sh — Emit the path to a working Python 3 interpreter.
# Tests each candidate with a real import to skip MS Store stubs.
# Source or call: PY=$(bash tools/ai_docs/find_python.sh)

CANDIDATES=(
    # Standard PATH lookups (fastest — try these first)
    "python3"
    "python"
    "py"

    # Windows: standard user installs (generic paths — no hardcoded username)
    "$LOCALAPPDATA/Programs/Python/Python313/python.exe"
    "$LOCALAPPDATA/Programs/Python/Python312/python.exe"
    "$LOCALAPPDATA/Programs/Python/Python311/python.exe"
    "$LOCALAPPDATA/Programs/Python/Python310/python.exe"
    "$LOCALAPPDATA/Programs/Python/Python39/python.exe"

    # Windows: system-wide installs
    "/c/Python313/python.exe"
    "/c/Python312/python.exe"
    "/c/Python311/python.exe"

    # Conda / Miniconda / Miniforge
    "$HOME/miniconda3/bin/python3"
    "$HOME/anaconda3/bin/python3"
    "$HOME/miniforge3/bin/python3"
    "$USERPROFILE/miniconda3/python.exe"
    "$USERPROFILE/anaconda3/python.exe"

    # pyenv
    "$HOME/.pyenv/shims/python3"
    "$HOME/.pyenv/shims/python"

    # Homebrew (macOS)
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"

    # System Python (Linux / macOS)
    "/usr/bin/python3"
)

for PY in "${CANDIDATES[@]}"; do
    [ -z "$PY" ] && continue
    # Require Python >= 3.8 and verify the interpreter actually runs
    # (skips Microsoft Store stubs and broken installs)
    if "$PY" -c "import sys; assert sys.version_info >= (3, 8)" >/dev/null 2>&1; then
        echo "$PY"
        exit 0
    fi
done

# No working Python 3.8+ found.
# Add PYTHON_BIN to tools/ai_docs/config.sh to point to your interpreter.
exit 1
