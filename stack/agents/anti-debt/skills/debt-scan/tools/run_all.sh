#!/usr/bin/env bash
# run_all.sh — Orchestrate all deterministic scanners for the anti-debt agent.
#
# Usage: ./run_all.sh [path-to-repo]
#
# Output:
#   .debt-scan-tmp/{code,security,deps}.json  — raw findings per scanner
#   .debt-scan-tmp/findings.json              — aggregated output (pre-Critic)
#   .debt-scan.json                           — final report (caller may invoke Critic afterwards)
#
# Exit codes:
#   0 — success (even if findings were found)
#   1 — fatal error (no language detected, etc.)

set -uo pipefail

ROOT="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${ROOT}/.debt-scan-tmp"
mkdir -p "$OUT_DIR"

if [ ! -d "$ROOT" ]; then
    echo "{\"error\":\"not a directory: $ROOT\"}" >&2
    exit 1
fi

cd "$ROOT" || exit 1

echo "[scan_code] running..." >&2
python3 "$SCRIPT_DIR/scan_code.py" "$ROOT" > "$OUT_DIR/code.json" 2>"$OUT_DIR/code.err" || \
    echo '{"language":"unknown","findings":[],"warning":"scan_code failed"}' > "$OUT_DIR/code.json"

echo "[scan_security] running..." >&2
python3 "$SCRIPT_DIR/scan_security.py" "$ROOT" > "$OUT_DIR/security.json" 2>"$OUT_DIR/security.err" || \
    echo '{"tools_installed":[],"findings":[],"warning":"scan_security failed"}' > "$OUT_DIR/security.json"

echo "[scan_deps] running..." >&2
python3 "$SCRIPT_DIR/scan_deps.py" "$ROOT" > "$OUT_DIR/deps.json" 2>"$OUT_DIR/deps.err" || \
    echo '{"tools_installed":[],"findings":[],"warning":"scan_deps failed"}' > "$OUT_DIR/deps.json"

echo "[aggregate] running..." >&2
python3 "$SCRIPT_DIR/aggregate.py" "$OUT_DIR" "$ROOT/.debt-scan.json" 2>"$OUT_DIR/aggregate.err" || \
    echo '{"error":"aggregate failed"}' > "$ROOT/.debt-scan.json"

echo "[done] see $ROOT/.debt-scan.json" >&2
echo "[next] invoke the Critic Engine (skills/critic/SKILL.md) to validate findings" >&2
exit 0
