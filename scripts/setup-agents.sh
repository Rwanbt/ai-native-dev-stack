#!/usr/bin/env bash
# setup-agents.sh — POSIX entry point for the global stack installer.
#
# The installer itself is scripts/install_agents.py: one cross-platform
# implementation instead of one per shell. This script only locates a working
# Python and hands over, so `bash scripts/setup-agents.sh` keeps working
# everywhere it used to.
#
# Windows without Git Bash: use scripts/setup-agents.ps1, or call
# `python scripts/install_agents.py` directly.
#
# Usage:
#   bash scripts/setup-agents.sh              # install the global stack
#   bash scripts/setup-agents.sh --dry-run    # show what would happen
#   bash scripts/setup-agents.sh --check      # verify an existing install
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALLER="$SCRIPT_DIR/install_agents.py"

PY="$(bash "$SCRIPT_DIR/../tools/ai_docs/find_python.sh" 2>/dev/null || true)"
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
  echo "ERROR: no Python 3.8+ found. Install Python, or set PYTHON_BIN in tools/ai_docs/config.sh." >&2
  exit 1
fi

exec "$PY" "$INSTALLER" "$@"
