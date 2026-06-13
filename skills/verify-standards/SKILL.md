---
name: verify-standards
description: |
  Project quality governance scorecard — verifies coding standards compliance
  across three enforcement tiers: CI gates, AI assistant rules (CLAUDE.md),
  and team governance (CODEOWNERS, RFC process).
  Produces a scored checklist with the next recommended action.
  Adapt the check list to your project's quality standards.
  Use when: "verify standards", "quality check", "standards audit",
  "check compliance", "how healthy is the codebase?".
  Proactively suggest before a major push, at the start of a long session,
  or after a significant refactor.
origin: generic
---

# Project Quality Standards — Governance Scorecard

Follow every step. Use real tool calls — never assume file state.
**Customize the checklists below for your project before using this skill.**

---

## STEP 0 — Context

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel)
echo "Project: $(basename $PROJECT_ROOT)"
echo "Branch:  $(git branch --show-current)"
echo "Commits: $(git rev-list --count HEAD) total"
```

---

## TIER 1 — CI Gates (automated enforcement)

These checks run in CI on every PR. Verify they are configured and passing locally.

```bash
# Rust: zero warnings
cargo clippy --lib --no-deps -- -D warnings 2>&1 | tail -5

# Rust: all tests pass
cargo test --lib 2>&1 | tail -5

# C++ (if applicable): build with zero new warnings
# cmake --build build/ --config Release 2>&1 | grep -E "warning:|error:" | head -10

# LOC gate: no file exceeds 1500 lines (adjust threshold to your project)
find src -name "*.cpp" -o -name "*.h" -o -name "*.rs" 2>/dev/null | while read F; do
  LINES=$(wc -l < "$F")
  [ "$LINES" -gt 1500 ] && echo "OVERSIZED: $F ($LINES lines)"
done
```

Mark each check: ✅ PASS · ⚠️ WARN · ❌ FAIL

---

## TIER 2 — AI Assistant Rules (AGENTS.md + CLAUDE.md / project instructions)

These are rules the AI assistant enforces proactively during development.

### 2a — Cross-tool portability (AGENTS.md)

```bash
# AGENTS.md at project root — cross-tool rules (Claude Code, Cursor, Codex, Copilot)
[ -f AGENTS.md ] && echo "AGENTS.md OK ($(wc -l < AGENTS.md) lines)" || echo "MISSING — run: cp /path/to/ai-native-dev-stack/AGENTS.md ."

# CLAUDE.md references AGENTS.md via @include
[ -f CLAUDE.md ] && grep -q "@AGENTS.md" CLAUDE.md \
  && echo "@AGENTS.md present in CLAUDE.md" \
  || echo "CLAUDE.md does not reference @AGENTS.md — add '@AGENTS.md' near the top"
```

- [ ] `AGENTS.md` present at project root (cross-tool portability)
- [ ] `CLAUDE.md` includes `@AGENTS.md` so rules load in Claude Code automatically

### 2b — Project-specific rules (CLAUDE.md)

```bash
# CLAUDE.md exists and is substantial
[ -f CLAUDE.md ] && echo "EXISTS ($(wc -l < CLAUDE.md) lines)" || echo "MISSING"

# Check for key sections (adapt to your project)
grep -c "Thread\|Real.time\|Forbidden\|Constraint" CLAUDE.md 2>/dev/null && echo "RT rules present" || echo "RT rules missing"
grep -c "naming\|convention\|pattern" CLAUDE.md 2>/dev/null && echo "Conventions present" || echo "Missing"
grep -c "pre.commit\|build\|test" CLAUDE.md 2>/dev/null && echo "Build rules present" || echo "Missing"
grep -c "error\|unwrap\|Result\|catch" CLAUDE.md 2>/dev/null && echo "Error handling present" || echo "Missing"
```

Key areas to verify are documented (customize for your project):
- [ ] Naming conventions (language, style, abbreviations)
- [ ] Thread model and real-time constraints (if applicable)
- [ ] Forbidden patterns (globals, singletons, unsafe alloc in hot paths)
- [ ] Build and pre-commit workflow
- [ ] Error handling policy (`unwrap()` rules, exception policy)
- [ ] File size thresholds and LOC budgets

---

## TIER 3 — Team Governance (human process)

These require human action to set up and maintain.

```bash
# Architecture Decision Records
ADR_COUNT=$(ls docs/adr/*.md 2>/dev/null | grep -v README | wc -l)
echo "ADRs: $ADR_COUNT"

# CONTRIBUTING.md
[ -f CONTRIBUTING.md ] && echo "CONTRIBUTING.md OK" || echo "MISSING"

# CODEOWNERS (GitHub ownership map)
[ -f .github/CODEOWNERS ] && echo "CODEOWNERS OK" || echo "MISSING (recommended for teams)"

# RFC process
[ -d docs/rfcs ] && echo "RFC dir OK ($(ls docs/rfcs/*.md 2>/dev/null | wc -l) RFCs)" || echo "No RFC dir"

# CHANGELOG
[ -f CHANGELOG.md ] || [ -f CHANGELOG ] && echo "CHANGELOG OK" || echo "MISSING"
```

---

## STEP 4 — Scorecard

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  QUALITY STANDARDS — SCORECARD
  Project: <name> · Branch: <branch>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tier 1 — CI Gates            N/M  [results]
Tier 2 — CLAUDE.md Rules     N/M  [results]
Tier 3 — Team Governance     N/M  [results]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SCORE: X/Y  |  PASS: A  WARN: B  FAIL: C
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## STEP 5 — Next recommended action

Based on the results, recommend ONE concrete next action:

- If any Tier 1 CI check fails → fix it now (stop-the-line rule)
- If CLAUDE.md is missing key sections → add them before next session
- If ADR count is 0 → write ADR-0001 for the most recent architectural decision
- If CODEOWNERS is missing on a team project → create it (15 min, high value)
- If all green → "Standards compliant. No action needed."

---

## Customization guide

This skill is a template. Before using it on your project:

1. **Replace Tier 1 commands** with your actual CI checks (language, tools, thresholds)
2. **Replace Tier 2 checklist** with your project's CLAUDE.md sections
3. **Add project-specific checks** (e.g., security scan, coverage gate, performance budget)
4. **Adjust LOC threshold** (default 1500 — tighten to 800 once codebase is healthy)

Save the customized skill as `.claude/skills/verify-standards/SKILL.md` in your project.
