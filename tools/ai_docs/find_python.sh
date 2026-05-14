#!/usr/bin/env bash
# find_python.sh — Emit the path to a working Python 3 interpreter.
# Tests each candidate with a real import to skip MS Store stubs.
# Source or call: PY=$(bash tools/ai_docs/find_python.sh)

CANDIDATES=(
    "/c/Users/barat/AppData/Local/Android/Sdk/ndk/27.0.12077973/toolchains/llvm/prebuilt/windows-x86_64/python3/python.exe"
    "/c/Users/barat/.lmstudio/extensions/backends/vendor/_amphibian/cpython3.11-win-x86@7/python.exe"
    "/c/Users/barat/.lmstudio/extensions/backends/vendor/_amphibian/cpython3.11-win-x86@6/python.exe"
    "/c/Users/barat/.lmstudio/extensions/backends/vendor/_amphibian/cpython3.11-win-x86@5/python.exe"
    "python3"
    "python"
)

for PY in "${CANDIDATES[@]}"; do
    # Test that the interpreter actually runs (skips MS Store stubs that exit with error)
    if "$PY" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        echo "$PY"
        exit 0
    fi
done

echo ""
exit 1
