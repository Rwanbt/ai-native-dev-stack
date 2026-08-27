#!/usr/bin/env bash
# install.sh — POSIX entry point for the per-project installer.
#
# The installer itself is install.py: one cross-platform implementation
# instead of one per shell. This script only locates a working Python and
# hands over, so `bash install.sh` keeps working everywhere it used to.
#
# Windows without Git Bash:  python install.py [options]
#
# Usage:
#   bash install.sh [--project-root PATH] [--with-gstack] [--gstack-ref REF] [--dry-run]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PY="$(bash "$SCRIPT_DIR/tools/ai_docs/find_python.sh" 2>/dev/null || true)"
if [ -z "$PY" ]; then
  for CANDIDATE in python3 python py; do
    if command -v "$CANDIDATE" >/dev/null 2>&1 &&
       "$CANDIDATE" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
      PY="$CANDIDATE"
      break
    fi
  done
fi

if [ -z "$PY" ]; then
  echo "ERROR: no Python 3.8+ found. Install Python and retry." >&2
  exit 1
fi

exec env PYTHONIOENCODING=utf-8 "$PY" "$SCRIPT_DIR/install.py" "$@"
