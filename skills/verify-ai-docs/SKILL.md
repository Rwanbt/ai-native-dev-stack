---
name: verify-ai-docs
description: |
  Full AI optimization stack health check for large codebases (C++, Rust, or any language).
  9-tier scorecard: AI docs, graphify dependency graph, Obsidian memory vault,
  Claude Code memory, project quality gates, and skills ecosystem.
  Auto-fixes stale summaries, stale graphify graph, missing hooks.
  Works for any new contributor — prints install guide when stack is missing.
  Use when: "verify ai docs", "check ai stack", "infrastructure IA à jour ?",
  "tout est à jour ?", "vérifier l'optimisation IA", "ai health check".
  Proactively suggest: after Track B extractions, before a major push,
  when a new contributor joins, or at the start of a long session.
origin: generic
---

# AI Optimization Stack — Full Health Check

Follow every step in order. Use real tool calls — never assume file state.
Project root is detected via `git rev-parse --show-toplevel`. Source `tools/ai_docs/config.sh` for machine paths.

---

## STEP 0 — Load config

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
[ -f "$PROJECT_ROOT/tools/ai_docs/config.sh" ] && source "$PROJECT_ROOT/tools/ai_docs/config.sh"

# Defaults if config missing
GRAPHIFY_BIN="${GRAPHIFY_BIN:-graphify}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/Obsidian}"
OBSIDIAN_PROJECT_DIR="${OBSIDIAN_PROJECT_DIR:-MyProject}"
OBSIDIAN_MEMORY_FILE="${OBSIDIAN_MEMORY_FILE:-$OBSIDIAN_PROJECT_DIR/_memory/memory.md}"
OBSIDIAN_LOG_FILE="${OBSIDIAN_LOG_FILE:-LOG.md}"
CLAUDE_MEMORY_ROOT="${CLAUDE_MEMORY_ROOT:-$HOME/.claude/projects}"
CLAUDE_MEMORY_KEY="${CLAUDE_MEMORY_KEY:-}"
SKILLS_DIR="${SKILLS_DIR:-.claude/skills}"
```

**Tracked modules** — customize this list for your project structure.
Read `tools/ai_docs/config.sh` or `generate_all.py` to find the canonical list.
Example (Seno DAW):
```
app/Source/Core/Audio    app/Source/Core/IO      app/Source/Core/Edit
app/Source/Core/Export   app/Source/Core/Streaming  app/Source/Core/Midi
app/Source/Core/Recording  app/Source/Core/Script  app/Source/Core/Input
app/Source/Core/Undo     app/Source/Core/Diagnostics  app/Source/Core/App
app/Source/UI            rust_dsp/src
```

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

Thresholds: `generate_ai_summary.py` ≥ 80 · `update_on_edit.py` ≥ 50 · `generate_all.py` ≥ 35 · `run_hook.sh` ≥ 10 · `find_python.sh` ≥ 8

❌ FAIL on any missing file → stop and print install guide (Step 9).

---

## TIER 2 — AI Documentation

### 2a — REALTIME_RULES.md
```bash
[ -f docs/REALTIME_RULES.md ] && echo "EXISTS $(wc -l < docs/REALTIME_RULES.md) lines" || echo "MISSING"
```
PASS if exists ≥ 40 lines.

### 2b — AI_CONTEXT.md per tracked module
```bash
for M in app/Source/Core/Audio app/Source/Core/IO app/Source/Core/Edit \
  app/Source/Core/Export app/Source/Core/Streaming app/Source/Core/Midi \
  app/Source/Core/Recording app/Source/Core/Script app/Source/Core/Input \
  app/Source/Core/Undo app/Source/Core/Diagnostics app/Source/Core/App \
  app/Source/UI rust_dsp; do
  [ -f "$M/AI_CONTEXT.md" ] && echo "OK $M" || echo "MISSING $M"
done
```

### 2c — Orphan detection (new modules without AI_CONTEXT.md)
```bash
for D in app/Source/Core/*/; do
  HAS_SRC=$(find "$D" -maxdepth 1 \( -name "*.h" -o -name "*.cpp" \) 2>/dev/null | head -1)
  [ -n "$HAS_SRC" ] && [ ! -f "${D}AI_CONTEXT.md" ] && echo "ORPHAN: $D"
done
```
`Core/Types/` is exempt (pure data headers, no service logic).
Each orphan = ⚠️ WARN — print AI_CONTEXT template in Step 8.

---

## TIER 3 — AI_SUMMARY Freshness

```bash
for M in app/Source/Core/Audio app/Source/Core/IO app/Source/Core/Edit \
  app/Source/Core/Export app/Source/Core/Streaming app/Source/Core/Midi \
  app/Source/Core/Recording app/Source/Core/Script app/Source/Core/Input \
  app/Source/Core/Undo app/Source/Core/Diagnostics app/Source/Core/App \
  app/Source/UI; do
  S="$M/AI_SUMMARY.md"
  [ ! -f "$S" ] && echo "MISSING $M" && continue
  STALE=$(find "$M" -maxdepth 1 \( -name "*.h" -o -name "*.cpp" \) -newer "$S" 2>/dev/null | head -1)
  [ -n "$STALE" ] && echo "STALE $M ($(basename $STALE))" || echo "OK $M"
done
# rust_dsp
S="rust_dsp/src/AI_SUMMARY.md"
[ ! -f "$S" ] && echo "MISSING rust_dsp/src" || {
  STALE=$(find rust_dsp/src -maxdepth 1 -name "*.rs" -newer "$S" 2>/dev/null | head -1)
  [ -n "$STALE" ] && echo "STALE rust_dsp/src ($(basename $STALE))" || echo "OK rust_dsp/src"
}
```

⚠️ WARN = stale → queued for auto-fix in Step 8.

---

## TIER 4 — Automation Chain (PostToolUse hook)

```bash
# 4a — Hook registered
grep -c "run_hook.sh" .claude/settings.json

# 4b — Python detection
PY=$(bash tools/ai_docs/find_python.sh)
[ -n "$PY" ] && "$PY" --version && echo "PYTHON_OK: $PY" || echo "PYTHON_MISSING"

# 4c — Functional end-to-end test
echo "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$PROJECT_ROOT/path/to/any/source/file.cpp\"}}" \
  | bash tools/ai_docs/run_hook.sh
```

PASS 4c if output contains "Updated".

---

## TIER 5 — graphify (Dependency Graph)

### 5a — Binary available
```bash
"$GRAPHIFY_BIN" --version 2>/dev/null && echo "GRAPHIFY_OK" || \
  (which graphify 2>/dev/null && echo "GRAPHIFY_OK (PATH)" || echo "GRAPHIFY_MISSING")
```

### 5b — graph.json exists
```bash
[ -f graphify-out/graph.json ] && echo "EXISTS $(du -h graphify-out/graph.json | cut -f1)" || echo "MISSING"
[ -f graphify-out/GRAPH_REPORT.md ] && echo "REPORT OK" || echo "REPORT MISSING"
```

### 5c — Graph freshness
```bash
NEWEST=$(find src -name "*.cpp" -o -name "*.h" -o -name "*.rs" 2>/dev/null \
  | xargs ls -t 2>/dev/null | head -1)
[ -n "$NEWEST" ] && [ graphify-out/graph.json -nt "$NEWEST" ] \
  && echo "GRAPH FRESH" || echo "GRAPH STALE ($(basename $NEWEST) is newer)"
```

⚠️ WARN if stale → auto-fix: `"$GRAPHIFY_BIN" update .` in Step 8.
❌ FAIL if binary missing → instructions in Step 9.

---

## TIER 6 — Obsidian Memory Vault

```bash
# Vault root
[ -d "$OBSIDIAN_VAULT" ] && echo "VAULT OK: $OBSIDIAN_VAULT" || echo "VAULT MISSING: $OBSIDIAN_VAULT"

# Project subfolder
[ -d "$OBSIDIAN_VAULT/$OBSIDIAN_PROJECT_DIR" ] \
  && echo "PROJECT DIR OK" || echo "PROJECT DIR MISSING"

# memory.md (the project AI memory note)
MEM="$OBSIDIAN_VAULT/$OBSIDIAN_MEMORY_FILE"
[ -f "$MEM" ] && echo "MEMORY OK ($(wc -l < $MEM) lines)" || echo "MEMORY MISSING: $MEM"

# LOG.md (global chronological session log)
LOG="$OBSIDIAN_VAULT/$OBSIDIAN_LOG_FILE"
[ -f "$LOG" ] || { echo "LOG MISSING: $LOG"; }
if [ -f "$LOG" ]; then
  # Check last entry is within 7 days
  LAST_MODIFIED=$(find "$LOG" -mtime -7 2>/dev/null)
  [ -n "$LAST_MODIFIED" ] && echo "LOG RECENT (< 7 days)" || echo "LOG STALE (> 7 days since last session)"
fi

# SCHEMA.md
[ -f "$OBSIDIAN_VAULT/SCHEMA.md" ] && echo "SCHEMA OK" || echo "SCHEMA MISSING (optional)"
```

⚠️ WARN if memory or log stale/missing (vault must exist for PASS).

---

## TIER 7 — Claude Code Memory System

```bash
# Locate project memory directory
if [ -n "$CLAUDE_MEMORY_KEY" ]; then
  MEM_DIR="$CLAUDE_MEMORY_ROOT/$CLAUDE_MEMORY_KEY/memory"
else
  MEM_DIR=$(find "$CLAUDE_MEMORY_ROOT" -name "MEMORY.md" 2>/dev/null | head -1 | xargs dirname)
fi

[ -d "$MEM_DIR" ] && echo "MEMORY DIR OK: $MEM_DIR" || echo "MEMORY DIR MISSING"
[ -f "$MEM_DIR/MEMORY.md" ] && echo "MEMORY.md OK ($(wc -l < $MEM_DIR/MEMORY.md) lines)" || echo "MEMORY.md MISSING"

# Warn if MEMORY.md > 200 lines (truncation risk)
if [ -f "$MEM_DIR/MEMORY.md" ]; then
  LINES=$(wc -l < "$MEM_DIR/MEMORY.md")
  [ "$LINES" -gt 200 ] && echo "WARN MEMORY.md $LINES lines — truncation risk, prune old entries"
fi

# Count memory topic files
TOPIC_COUNT=$(find "$MEM_DIR" -name "*.md" ! -name "MEMORY.md" 2>/dev/null | wc -l)
echo "Topic files: $TOPIC_COUNT"
```

---

## TIER 8 — Project Quality Gates

```bash
# CLAUDE.md (project)
[ -f CLAUDE.md ] && echo "CLAUDE.md OK ($(wc -l < CLAUDE.md) lines)" || echo "CLAUDE.md MISSING"

# ARCHITECTURE.md
[ -f docs/ARCHITECTURE.md ] \
  && echo "ARCHITECTURE.md OK ($(wc -l < docs/ARCHITECTURE.md) lines)" \
  || echo "ARCHITECTURE.md MISSING"

# ADRs
ADR_COUNT=$(ls docs/adr/*.md 2>/dev/null | grep -v README | wc -l)
[ "$ADR_COUNT" -gt 0 ] && echo "ADRs OK ($ADR_COUNT records)" || echo "ADR dir EMPTY"

# CONTRIBUTING.md
[ -f CONTRIBUTING.md ] && echo "CONTRIBUTING.md OK" || echo "CONTRIBUTING.md MISSING"

# docs/REALTIME_RULES.md (standalone)
[ -f docs/REALTIME_RULES.md ] && echo "REALTIME_RULES.md OK" || echo "REALTIME_RULES.md MISSING"
```

---

## TIER 9 — Skills Ecosystem

```bash
for S in verify-ai-docs realtime-audio cpp-coding-standards cpp-testing; do
  [ -f "$SKILLS_DIR/$S/SKILL.md" ] \
    && echo "OK $S ($(wc -l < $SKILLS_DIR/$S/SKILL.md) lines)" \
    || echo "MISSING $S"
done

# Check gstack global skills (verify-standards, audio-validate, clap-release)
GSTACK_SKILLS="${GSTACK_SKILLS:-$HOME/.claude/skills/gstack}"
for S in verify-standards audio-validate clap-release; do
  find "$GSTACK_SKILLS" -name "SKILL.md" 2>/dev/null | xargs grep -l "^name: $S" 2>/dev/null | head -1 | \
    { read F; [ -n "$F" ] && echo "OK $S (gstack)" || echo "MISSING $S (gstack)"; }
done
```

---

## STEP 6 — Scorecard

Print the full scorecard:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AI OPTIMIZATION STACK — FULL HEALTH SCORECARD
  Project: <YourProject> · Date: YYYY-MM-DD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tier 1 — Core Scripts           (5/5)   [results]
Tier 2 — AI Documentation       (N/15)  [results]
Tier 3 — AI_SUMMARY Freshness   (N/14)  [results]
Tier 4 — Automation Chain       (3/3)   [results]
Tier 5 — graphify Graph         (3/3)   [results]
Tier 6 — Obsidian Memory Vault  (N/5)   [results]
Tier 7 — Claude Code Memory     (N/3)   [results]
Tier 8 — Project Quality Gates  (N/5)   [results]
Tier 9 — Skills Ecosystem       (N/7)   [results]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SCORE: X/Y  |  PASS: A  WARN: B  FAIL: C
  Status: [OPERATIONAL / DEGRADED / BROKEN]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Replace "MyProject" in the header with your actual project name.

Status:
- **OPERATIONAL** — 0 FAILs
- **DEGRADED** — FAILs only in Tiers 2/3/6/7/8/9 (docs/memory/quality)
- **BROKEN** — FAIL in Tier 1, 4 hook, or 4 Python

---

## STEP 7 — Auto-fix (run automatically)

### Fix stale AI_SUMMARY.md
```bash
PY=$(bash tools/ai_docs/find_python.sh)
PYTHONIOENCODING=utf-8 "$PY" tools/ai_docs/generate_all.py
```

### Fix stale graphify graph
```bash
"$GRAPHIFY_BIN" update . && echo "Graph updated"
```

### Fix missing PostToolUse hook
If Tier 4a failed: edit `.claude/settings.json` to add:
```json
{ "type": "command", "command": "bash <PROJECT_ROOT>/tools/ai_docs/run_hook.sh" }
```
Into the `PostToolUse → Edit|Write → hooks` array.

---

## STEP 8 — Report-only fixes

### Missing AI_CONTEXT.md → print template
```markdown
# AI_CONTEXT — <ModuleName>

## Purpose
<2-3 sentences: what this module does.>

## Thread model
| Component | Thread | Notes |
|---|---|---|
| <fn> | Main / Audio / Export | <notes> |

## Constraints
- <key constraint>

## Forbidden
- <what must never happen here>

## Common patterns
```cpp
// Example
```

## See also
- ADR-XXXX
```
→ Fill in, save, then re-run `/verify-ai-docs`.

### Missing Obsidian memory.md → print frontmatter template
```yaml
---
project: myproject
type: architecture
tags: [myproject, memory]
summary: "AI session memory for MyProject — one sentence, 15-25 words."
created: YYYY-MM-DD
updated: YYYY-MM-DD
related: [[INDEX]], [[MyProject/CLAUDE]]
---
```

---

## STEP 9 — New contributor install guide

Print ONLY if Tier 1 or Tier 4 Python had FAILs:

```
AI OPTIMIZATION STACK — INSTALL GUIDE
======================================

1. SCRIPTS (already committed to git — nothing to install)
   tools/ai_docs/generate_ai_summary.py
   tools/ai_docs/update_on_edit.py
   tools/ai_docs/generate_all.py
   tools/ai_docs/run_hook.sh
   tools/ai_docs/find_python.sh

2. PYTHON — Install Python 3.8+ and add to PATH, or set PYTHON_BIN in config.sh

3. HOOK — Add to .claude/settings.json → hooks.PostToolUse → Edit|Write:
   { "type": "command", "command": "bash <ROOT>/tools/ai_docs/run_hook.sh" }

4. CONFIG — Copy and edit tools/ai_docs/config.sh:
   - Set GRAPHIFY_BIN to your graphify binary path
   - Set OBSIDIAN_VAULT to your vault root
   - Set CLAUDE_MEMORY_KEY to match your ~/.claude/projects/ subfolder

5. GRAPHIFY — Install from https://github.com/graphify/graphify
   Then run: graphify . (in project root, once)

6. GENERATE — Run: python tools/ai_docs/generate_all.py

7. VERIFY — Run: /verify-ai-docs
```

---

## Final summary line

- All PASS:   `AI optimization stack fully operational. No action needed.`
- WARNs only: `Stack operational. N auto-fixes applied. N warnings remain.`
- DEGRADED:   `Stack degraded — see above for missing docs/memory items.`
- BROKEN:     `Stack broken — Tier 1 or 4 failures require manual setup.`
