---
name: verify-ai-docs
description: |
  Full AI optimization stack health check for any codebase.
  9-tier scorecard: AI docs, dependency graph, Obsidian memory vault,
  Claude Code memory, project quality gates, and skills ecosystem.
  Works for any language (C++, Rust, TypeScript, Python, Go, Java, etc.)
  and any project structure — no hardcoded paths.
  Auto-fixes stale summaries, stale graph, missing hooks.
  Prints install guide for new contributors when stack is missing.
  Use when: "verify ai docs", "check ai stack", "is everything up to date?",
  "ai health check", "verify optimization stack", "check my ai setup".
  Proactively suggest before a major push, when a new contributor joins,
  or at the start of a long coding session.
origin: generic
---

# AI Optimization Stack — Full Health Check

Follow every step in order. Use real tool calls — never assume file state.
Project root is detected automatically from git. Config is loaded from
`tools/ai_docs/config.sh` (machine-specific, git-ignored).

---

## STEP 0 — Load config and detect project

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
echo "Project root: $PROJECT_ROOT"

[ -f "$PROJECT_ROOT/tools/ai_docs/config.sh" ] \
  && source "$PROJECT_ROOT/tools/ai_docs/config.sh" \
  && echo "Config loaded" \
  || echo "No config.sh (using defaults)"

# Defaults
GRAPHIFY_BIN="${GRAPHIFY_BIN:-graphify}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/Obsidian}"
OBSIDIAN_PROJECT_DIR="${OBSIDIAN_PROJECT_DIR:-$(basename $PROJECT_ROOT)}"
OBSIDIAN_MEMORY_FILE="${OBSIDIAN_MEMORY_FILE:-$OBSIDIAN_PROJECT_DIR/_memory/memory.md}"
OBSIDIAN_LOG_FILE="${OBSIDIAN_LOG_FILE:-LOG.md}"
CLAUDE_MEMORY_ROOT="${CLAUDE_MEMORY_ROOT:-$HOME/.claude/projects}"
CLAUDE_MEMORY_KEY="${CLAUDE_MEMORY_KEY:-}"
SKILLS_DIR="${SKILLS_DIR:-.claude/skills}"
```

**Module discovery** — modules are identified by the presence of `AI_CONTEXT.md`.
No hardcoded list needed. Run:
```bash
find "$PROJECT_ROOT" -name "AI_CONTEXT.md" \
  -not -path "*/.git/*" \
  -not -path "*/node_modules/*" \
  -not -path "*/vendor/*" \
  -not -path "*/__pycache__/*" \
  | sort
```
This shows all tracked modules. Use this list for Tiers 2 and 3.

---

## TIER 1 — Core Scripts

```bash
for F in \
  tools/ai_docs/generate_ai_summary.py \
  tools/ai_docs/update_on_edit.py \
  tools/ai_docs/generate_all.py \
  tools/ai_docs/run_hook.sh \
  tools/ai_docs/find_python.sh; do
  [ -f "$F" ] && echo "EXISTS $(wc -l < $F) $F" || echo "MISSING $F"
done
```

Thresholds: `generate_ai_summary.py` ≥ 80 · `update_on_edit.py` ≥ 50
`generate_all.py` ≥ 35 · `run_hook.sh` ≥ 10 · `find_python.sh` ≥ 20

❌ FAIL on any missing file → skip remaining tiers and print install guide (Step 9).

---

## TIER 2 — AI Documentation

### 2a — Constraint rules doc (optional but recommended)
```bash
# Check for a standalone constraint/rules document (any name)
for F in docs/REALTIME_RULES.md docs/RULES.md docs/CONSTRAINTS.md docs/THREADING.md; do
  [ -f "$F" ] && echo "OK $F ($(wc -l < $F) lines)" && break
done
```
⚠️ WARN if missing — recommended for any project with RT, threading, or domain constraints.

### 2b — AI_CONTEXT.md coverage (auto-discovered)
```bash
# Find all directories with source files
TOTAL_SRC_DIRS=$(find . -not -path "*/.git/*" -not -path "*/node_modules/*" \
  -not -path "*/vendor/*" -not -path "*/build/*" -not -path "*/dist/*" \
  -not -path "*/target/*" -not -path "*/__pycache__/*" \
  \( -name "*.cpp" -o -name "*.h" -o -name "*.rs" -o -name "*.ts" \
     -o -name "*.py" -o -name "*.go" -o -name "*.java" -o -name "*.cs" \) \
  -printf "%h\n" 2>/dev/null | sort -u | wc -l)

# Count directories that have AI_CONTEXT.md
COVERED=$(find . -name "AI_CONTEXT.md" -not -path "*/.git/*" \
  -not -path "*/node_modules/*" | wc -l)

echo "Modules with AI_CONTEXT.md: $COVERED"
echo "Total source directories:   $TOTAL_SRC_DIRS"

# List each tracked module
find . -name "AI_CONTEXT.md" -not -path "*/.git/*" \
  -not -path "*/node_modules/*" -not -path "*/vendor/*" \
  | sort | while read CTX; do
    DIR=$(dirname "$CTX")
    echo "OK: ${DIR#./}"
  done
```

### 2c — Orphan detection
Source directories with files but no `AI_CONTEXT.md`:
```bash
find . -not -path "*/.git/*" -not -path "*/node_modules/*" \
  -not -path "*/vendor/*" -not -path "*/build/*" -not -path "*/dist/*" \
  -not -path "*/target/*" -not -path "*/__pycache__/*" \
  \( -name "*.cpp" -o -name "*.h" -o -name "*.rs" -o -name "*.ts" \
     -o -name "*.py" -o -name "*.go" -o -name "*.java" \) \
  -printf "%h\n" 2>/dev/null | sort -u | while read D; do
    [ ! -f "$D/AI_CONTEXT.md" ] && echo "ORPHAN: ${D#./}"
  done | head -20
```
Each orphan = ⚠️ WARN. Print template from Step 8 for each.

---

## TIER 3 — AI_SUMMARY.md Freshness (auto-discovered)

```bash
find . -name "AI_CONTEXT.md" \
  -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/vendor/*" \
  | sort | while read CTX; do
    DIR=$(dirname "$CTX")
    SUMMARY="$DIR/AI_SUMMARY.md"
    NAME="${DIR#./}"

    if [ ! -f "$SUMMARY" ]; then
      echo "MISSING: $NAME"
    else
      # Check if any source file is newer than AI_SUMMARY.md
      STALE=$(find "$DIR" -maxdepth 1 \
        \( -name "*.cpp" -o -name "*.h" -o -name "*.rs" -o -name "*.ts" \
           -o -name "*.tsx" -o -name "*.py" -o -name "*.go" -o -name "*.java" \
           -o -name "*.cs" -o -name "*.swift" -o -name "*.kt" \) \
        -newer "$SUMMARY" 2>/dev/null | head -1)
      [ -n "$STALE" ] \
        && echo "STALE: $NAME ($(basename $STALE) is newer)" \
        || echo "OK: $NAME"
    fi
  done
```

⚠️ WARN if stale → queued for auto-fix in Step 7.

---

## TIER 4 — Automation Chain (PostToolUse hook)

### 4a — Hook registered
```bash
grep -c "run_hook.sh" .claude/settings.json 2>/dev/null \
  && echo "HOOK REGISTERED" || echo "HOOK MISSING"
```

### 4b — Python detection
```bash
PY=$(bash tools/ai_docs/find_python.sh)
[ -n "$PY" ] && "$PY" --version && echo "PYTHON_OK: $PY" || echo "PYTHON_MISSING"
```

### 4c — Functional end-to-end test
Pick any source file that exists in a tracked module and simulate an edit event:
```bash
# Find any source file inside a tracked module (has AI_CONTEXT.md in parent)
TEST_FILE=$(find . -name "AI_CONTEXT.md" -not -path "*/.git/*" \
  | head -1 | xargs dirname | xargs -I{} find {} -maxdepth 1 \
  \( -name "*.cpp" -o -name "*.h" -o -name "*.rs" -o -name "*.ts" \
     -o -name "*.py" -o -name "*.go" -o -name "*.java" \) 2>/dev/null | head -1)

if [ -n "$TEST_FILE" ]; then
  ABS_TEST="$PROJECT_ROOT/${TEST_FILE#./}"
  echo "Testing with: $ABS_TEST"
  echo "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$ABS_TEST\"}}" \
    | bash tools/ai_docs/run_hook.sh
else
  echo "SKIP — no source file found in tracked module"
fi
```
✅ PASS if output contains "Updated".

---

## TIER 5 — Dependency Graph (graphify or equivalent)

### 5a — Tool available
```bash
"$GRAPHIFY_BIN" --version 2>/dev/null && echo "GRAPHIFY_OK" || \
  (which graphify 2>/dev/null && echo "GRAPHIFY_OK (PATH)" || echo "GRAPHIFY_MISSING")
```
⚠️ WARN if missing (recommended, not required). Print install note in Step 8.

### 5b — Graph output exists
```bash
[ -f graphify-out/graph.json ] \
  && echo "EXISTS $(du -h graphify-out/graph.json | cut -f1)" \
  || echo "MISSING — run: graphify ."
```

### 5c — Graph freshness
```bash
NEWEST=$(find . -not -path "*/.git/*" -not -path "*/node_modules/*" \
  -not -path "*/build/*" -not -path "*/dist/*" -not -path "*/target/*" \
  \( -name "*.cpp" -o -name "*.h" -o -name "*.rs" -o -name "*.ts" \
     -o -name "*.py" -o -name "*.go" -o -name "*.java" \) \
  -newer graphify-out/graph.json 2>/dev/null | head -1)
[ -n "$NEWEST" ] \
  && echo "GRAPH STALE ($(basename $NEWEST) is newer)" \
  || echo "GRAPH FRESH"
```
⚠️ WARN if stale → auto-fix: `graphify update .`

---

## TIER 6 — Obsidian Memory Vault

```bash
# Vault root
[ -d "$OBSIDIAN_VAULT" ] \
  && echo "VAULT OK: $OBSIDIAN_VAULT" \
  || echo "VAULT MISSING: $OBSIDIAN_VAULT (set OBSIDIAN_VAULT in config.sh)"

# Project subfolder
[ -d "$OBSIDIAN_VAULT/$OBSIDIAN_PROJECT_DIR" ] \
  && echo "PROJECT DIR OK: $OBSIDIAN_PROJECT_DIR" \
  || echo "PROJECT DIR MISSING: $OBSIDIAN_VAULT/$OBSIDIAN_PROJECT_DIR"

# memory.md
MEM="$OBSIDIAN_VAULT/$OBSIDIAN_MEMORY_FILE"
[ -f "$MEM" ] \
  && echo "MEMORY OK ($(wc -l < $MEM) lines)" \
  || echo "MEMORY MISSING: $MEM"

# LOG.md — global session journal
LOG="$OBSIDIAN_VAULT/$OBSIDIAN_LOG_FILE"
if [ -f "$LOG" ]; then
  RECENT=$(find "$LOG" -mtime -7 2>/dev/null)
  [ -n "$RECENT" ] && echo "LOG RECENT (< 7 days)" || echo "LOG STALE (> 7 days)"
else
  echo "LOG MISSING: $LOG"
fi

[ -f "$OBSIDIAN_VAULT/SCHEMA.md" ] && echo "SCHEMA OK" || echo "SCHEMA MISSING (optional)"
```

⚠️ WARN if memory missing or log stale. ❌ FAIL only if vault root doesn't exist.

---

## TIER 7 — Claude Code Memory System

```bash
# Find memory directory
if [ -n "$CLAUDE_MEMORY_KEY" ]; then
  MEM_DIR="$CLAUDE_MEMORY_ROOT/$CLAUDE_MEMORY_KEY/memory"
else
  MEM_DIR=$(find "$CLAUDE_MEMORY_ROOT" -name "MEMORY.md" 2>/dev/null \
    | head -1 | xargs -I{} dirname {})
fi

[ -d "$MEM_DIR" ] \
  && echo "MEMORY DIR OK: $MEM_DIR" \
  || echo "MEMORY DIR MISSING (set CLAUDE_MEMORY_KEY in config.sh)"

if [ -f "$MEM_DIR/MEMORY.md" ]; then
  LINES=$(wc -l < "$MEM_DIR/MEMORY.md")
  echo "MEMORY.md: $LINES lines"
  [ "$LINES" -gt 200 ] \
    && echo "WARN: > 200 lines — truncation risk, prune old entries" \
    || echo "OK"
fi

TOPIC_COUNT=$(find "$MEM_DIR" -name "*.md" ! -name "MEMORY.md" 2>/dev/null | wc -l)
echo "Topic files: $TOPIC_COUNT"
```

---

## TIER 8 — Project Quality Gates

```bash
# Project AI instructions
[ -f CLAUDE.md ] \
  && echo "CLAUDE.md OK ($(wc -l < CLAUDE.md) lines)" \
  || echo "CLAUDE.md MISSING — add project-level AI instructions"

# Architecture doc
for F in docs/ARCHITECTURE.md ARCHITECTURE.md; do
  [ -f "$F" ] && echo "ARCHITECTURE OK: $F ($(wc -l < $F) lines)" && break
done

# Decision records
ADR_COUNT=$(find docs/adr docs/decisions -name "*.md" 2>/dev/null \
  | grep -v README | wc -l)
[ "$ADR_COUNT" -gt 0 ] \
  && echo "Decision records: $ADR_COUNT" \
  || echo "No ADRs — consider docs/adr/ for architectural decisions"

# Contributing guide
for F in CONTRIBUTING.md docs/CONTRIBUTING.md; do
  [ -f "$F" ] && echo "CONTRIBUTING OK: $F" && break
done
```

---

## TIER 9 — Skills Ecosystem

```bash
# Project-local skills
echo "=== Local skills (.claude/skills/) ==="
find "$SKILLS_DIR" -name "SKILL.md" 2>/dev/null | sort | while read S; do
  NAME=$(basename $(dirname "$S"))
  echo "OK: $NAME ($(wc -l < $S) lines)"
done

# Count project skills
COUNT=$(find "$SKILLS_DIR" -name "SKILL.md" 2>/dev/null | wc -l)
echo "Total: $COUNT local skill(s)"

# Check for verify-ai-docs itself
[ -f "$SKILLS_DIR/verify-ai-docs/SKILL.md" ] \
  && echo "verify-ai-docs: PRESENT" \
  || echo "verify-ai-docs: MISSING — copy from ai-native-dev-stack repo"
```

---

## STEP 6 — Scorecard

Print the full scorecard using results from Tiers 1-9:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AI OPTIMIZATION STACK — HEALTH SCORECARD
  Project: <ProjectName> · <date>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tier 1 — Core Scripts          [N/5]  results
Tier 2 — AI Documentation      [N/M]  results
Tier 3 — AI_SUMMARY Freshness  [N/M]  results
Tier 4 — Automation Chain      [N/3]  results
Tier 5 — Dependency Graph      [N/3]  results
Tier 6 — Obsidian Vault        [N/5]  results
Tier 7 — Claude Code Memory    [N/3]  results
Tier 8 — Project Quality       [N/4]  results
Tier 9 — Skills Ecosystem      [N/M]  results

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SCORE: X/Y  |  PASS: A  WARN: B  FAIL: C
  Status: OPERATIONAL / DEGRADED / BROKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Status rules:
- **OPERATIONAL** — 0 FAILs (warnings are OK)
- **DEGRADED** — FAILs in Tiers 2/3/6/7/8/9 only
- **BROKEN** — FAIL in Tier 1 (scripts missing) or Tier 4 (Python/hook broken)

---

## STEP 7 — Auto-fix (execute automatically)

### Fix stale AI_SUMMARY.md (always)
```bash
PY=$(bash tools/ai_docs/find_python.sh)
PYTHONIOENCODING=utf-8 "$PY" tools/ai_docs/generate_all.py
```

### Fix stale dependency graph
```bash
"$GRAPHIFY_BIN" update . 2>/dev/null && echo "Graph updated" \
  || echo "graphify not available — skip"
```

### Fix missing PostToolUse hook
If Tier 4a FAILED — add to `.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "bash /absolute/path/to/tools/ai_docs/run_hook.sh"
      }]
    }]
  }
}
```
Use the absolute path to `run_hook.sh` in your project.

---

## STEP 8 — Report-only actions

### Missing AI_CONTEXT.md — print this template for each orphan
```markdown
# AI_CONTEXT — <ModuleName>

## Purpose
<2-3 sentences describing what this module does and why it's a separate module.>

## Thread model (if applicable)
| Function | Thread | Notes |
|---|---|---|
| `myFunction()` | Main thread | Synchronous, blocking OK |
| `processCallback()` | Worker / RT thread | No alloc, no blocking |

## Constraints
- <What must always be true in this module>
- <External invariant this module depends on>

## Forbidden
- <What must never happen in this module's code>

## Common patterns
```language
// Typical usage
module.doThing(arg);
```

## See also
- [Link to related module or ADR]
```
→ Fill in and save as `<module_dir>/AI_CONTEXT.md`, then re-run `/verify-ai-docs`.

### Missing graphify
```
Install: see https://github.com/graphify/graphify
Then run: graphify .   (from project root, once — takes 30-60s)
Update:   graphify update .   (fast, AST-only, run after large refactors)
```

---

## STEP 9 — New contributor install guide

Print ONLY when Tier 1 had FAILs (fresh machine):

```
AI-NATIVE DEV STACK — INSTALL GUIDE
=====================================

Repository: https://github.com/Rwanbt/ai-native-dev-stack

PREREQUISITES
  - Git repository (required)
  - Python 3.8+     (required for AI_SUMMARY generation)
  - Claude Code     (required for /verify-ai-docs skill)
  - graphify        (recommended for dependency graph)
  - Obsidian        (recommended for memory vault)

QUICK SETUP
  1. Scripts are already committed to the project repo.
     git pull   (gets tools/ai_docs/ + .claude/skills/)

  2. Register the PostToolUse hook:
     Edit .claude/settings.json and add the run_hook.sh command.
     See templates/settings_hook_example.json for the exact format.

  3. Set up machine config:
     cp tools/ai_docs/config.sh.example tools/ai_docs/config.sh
     Edit config.sh: set OBSIDIAN_VAULT, GRAPHIFY_BIN, CLAUDE_MEMORY_KEY

  4. Generate all AI_SUMMARY.md files:
     python tools/ai_docs/generate_all.py

  5. Verify:
     /verify-ai-docs   → should show OPERATIONAL
```

---

## Final summary

- All PASS: `AI optimization stack fully operational. No action needed.`
- WARNs only: `Stack operational. N auto-fixes applied. N warnings remain.`
- DEGRADED: `Stack degraded — see above for missing docs/memory/quality items.`
- BROKEN: `Stack broken — Tier 1 or 4 failures require manual intervention.`
