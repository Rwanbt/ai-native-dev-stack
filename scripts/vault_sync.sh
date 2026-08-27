#!/usr/bin/env bash
# vault_sync.sh — POSIX entry point for the vault sync.
# The implementation is scripts/vault_sync.py. Vault path: $1 or $OBSIDIAN_VAULT.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for PY in python3 python py; do
  if command -v "$PY" >/dev/null 2>&1 &&
     "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
    exec env PYTHONIOENCODING=utf-8 "$PY" "$SCRIPT_DIR/vault_sync.py" "$@"
  fi
done
echo "ERROR: no Python 3.8+ found — vault NOT synced." >&2
exit 1
