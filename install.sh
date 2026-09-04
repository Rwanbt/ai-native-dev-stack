#!/usr/bin/env bash
# install.sh — POSIX bootstrap for the AI-Native Dev Stack.
#
# It finds a Python and hands over. It holds no lifecycle logic: the single
# authority for installing, switching, uninstalling and updating is the
# lifecycle manager (ADR-0009), reached through install.py and then `ainative`.
#
# Windows without Git Bash:  python install.py [options]
#
# Usage:
#   bash install.sh                            # asks which profile
#   bash install.sh --profile standard
#   bash install.sh --profile verified --dry-run
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# find_python.sh accepts 3.8+, because the AI-docs tooling it was written for
# runs there. The lifecycle CLI needs 3.11+, so its answer is re-checked rather
# than trusted.
PY="$(bash "$SCRIPT_DIR/tools/ai_docs/find_python.sh" 2>/dev/null || true)"
if [ -n "$PY" ] &&
   ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
  PY=""
fi
if [ -z "$PY" ]; then
  for CANDIDATE in python3 python py; do
    if command -v "$CANDIDATE" >/dev/null 2>&1 &&
       "$CANDIDATE" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
      PY="$CANDIDATE"
      break
    fi
  done
fi

if [ -z "$PY" ]; then
  echo "ERROR: no Python 3.11+ found. Install Python and retry." >&2
  exit 1
fi

exec env PYTHONIOENCODING=utf-8 "$PY" "$SCRIPT_DIR/install.py" "$@"
