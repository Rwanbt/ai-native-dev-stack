#!/usr/bin/env bash
# test_validate.sh — zero-dependency tests for validate-commit.sh
# Usage: bash tests/test_validate.sh

BIN="$(cd "$(dirname "$0")/../bin" && pwd)/validate-commit.sh"
PASS=0
FAIL=0
FAILED_CASES=""

run_case() {
  local label="$1" cmd="$2" expect="$3"
  local input got raw

  # CRITICAL: build the JSON via python to avoid bash quote-escaping hell
  input=$(python -c "import json,sys; print(json.dumps({'tool_input':{'command':sys.argv[1]}}))" "$cmd")
  raw=$(printf '%s' "$input" | bash "$BIN" 2>&1)
  got=$(printf '%s' "$raw" | python -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('hookSpecificOutput',{}).get('permissionDecision','none'))
except Exception:
    print('parse_error')" 2>/dev/null || echo "exec_error")
  if [ "$got" = "$expect" ]; then
    echo "  PASS  $label"
    PASS=$((PASS+1))
  else
    echo "  FAIL  $label  (got=$got, expect=$expect)"
    echo "    RAW: $raw" | head -c 200
    echo ""
    FAIL=$((FAIL+1))
    FAILED_CASES="$FAILED_CASES
  - $label"
  fi
}

echo "Conventional Commits validator tests"
echo "======================================"

# PASS cases (allow)
run_case "feat with scope"          'git commit -m "feat(auth): add OAuth login"'                                 allow
run_case "fix without scope"        'git commit -m "fix: correct null deref in parser"'                           allow
run_case "feat with breaking bang"  'git commit -m "feat(api)!: drop v1 endpoints"'                               allow
run_case "perf with multi-word sc"  'git commit -m "perf(audio-thread): cache wasm modules"'                      allow
run_case "docs simple"             'git commit -m "docs(readme): update install steps"'                          allow
run_case "with --no-verify"         'git commit -m "anything goes here" --no-verify'                              allow
run_case "non-commit command"       'git status'                                                                allow
run_case "git commit with body"     'git commit -m "feat(x): add" -m "long body here" -m "footer"'                allow
run_case "git -C path commit"       'git -C /tmp/repo commit -m "feat(y): do thing"'                             allow

# ASK cases (rejected)
run_case "no type prefix"           'git commit -m "Added new feature"'                                          ask
run_case "uppercase type"           'git commit -m "FEAT(auth): add oauth"'                                     ask
run_case "trailing period"          'git commit -m "feat: Add OAuth."'                                          ask
run_case "scope with spaces"        'git commit -m "feat(authentication layer): add oauth"'                      ask
run_case "subject too long"         'git commit -m "feat(auth): add oauth login flow with multi factor auth and remember me cookie support"' ask
run_case "invalid type"             'git commit -m "fixed the bug in the eq"'                                    ask
run_case "empty commit message"     'git commit -m ""'                                                          ask

# WARN cases (promoted to ASK per hook contract)
LONG_LINE=$(printf 'feat(api): %.0s' {1..20})
LONG_LINE="${LONG_LINE}drop endpoints"
run_case "first line > 100 chars"   "git commit -m \"$LONG_LINE\""                                              ask
run_case "BREAKING CHANGE no bang"  'git commit -m "feat(api): drop endpoints" -m "BREAKING CHANGE: v1 removed"' ask

echo ""
echo "======================================"
echo "Result: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "Failed cases:$FAILED_CASES"
  exit 1
fi