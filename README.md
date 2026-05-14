# AI-Native Dev Stack

> A complete methodology and toolkit for making any large codebase immediately understandable by AI assistants — with automatic maintenance so context never goes stale.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Works with Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-green)](https://claude.ai/code)
[![Claude Code skill](https://img.shields.io/badge/skill-verify--ai--docs-purple)](skills/verify-ai-docs/SKILL.md)

---

## The Problem

Large codebases (60k+ lines, multi-language, multi-thread) overwhelm AI context windows. Without structure, every session starts from zero: the AI hallucinates architecture, misses real-time constraints, and proposes solutions that break the threading model.

The usual workarounds (dumping files into context, writing long prompts) don't scale. They're manual, they go stale, and they consume tokens on noise instead of signal.

## The Solution

A self-maintaining **AI optimization stack** — a set of structured documents, scripts, and hooks that keeps the AI permanently oriented without human intervention:

```
AI Context Files (per module)   ←  auto-updated on every file edit
Dependency Graph (graphify)     ←  re-indexed on demand or after big refactors
Real-time Rules (standalone)    ←  single file injected for RT-adjacent work
Memory Vault (Obsidian)         ←  persistent cross-session second brain
Claude Code Memory              ←  auto-generated session summaries
Skills Ecosystem                ←  domain-specific verification commands
PostToolUse Hook                ←  keeps everything in sync automatically
```

One command checks the health of the entire stack: `/verify-ai-docs`

---

## Stack Components

### 1. Module-Level AI Context (`AI_CONTEXT.md`)

Each source module gets a hand-written `AI_CONTEXT.md` that captures what no README does: **thread model, forbidden patterns, non-obvious constraints, and common call patterns**.

```
app/Source/Core/Audio/
├── AI_CONTEXT.md      ← hand-written: purpose, thread model, constraints
├── AI_SUMMARY.md      ← auto-generated: public types, functions, LOC table
├── PluginMgr.h
├── TrackFreezer.h
└── ...
```

**`AI_CONTEXT.md` covers:**
- Module purpose (2-3 sentences)
- Thread model table (which function runs on which thread)
- Constraints (what is allowed/forbidden)
- Common usage patterns with code examples
- Cross-references to ADRs and related modules

**`AI_SUMMARY.md` is auto-generated** from the source headers on every file edit via a PostToolUse hook. It always reflects the current public API: Host structs, free functions, LOC counts with size warnings.

### 2. Real-Time Rules (`docs/REALTIME_RULES.md`)

A standalone document covering all constraints for real-time (audio/video) thread code. Injected as context whenever working on RT-adjacent code, without loading the entire project documentation.

Key sections:
- Thread model diagram
- Audio callback absolute constraints (zero alloc, zero blocking, zero exceptions)
- Lock-free data handoff patterns
- Frozen Core zones (functions never refactored without review)
- Rust DSP rules (`unwrap()` forbidden in hot path, etc.)

### 3. Automatic Maintenance (PostToolUse Hook)

A Claude Code `PostToolUse` hook fires after every `Edit` or `Write` on a `.cpp`, `.h`, or `.rs` file. It detects which module was modified and regenerates that module's `AI_SUMMARY.md` in under a second.

```
Edit TrackFreezer.cpp
    → hook fires → update_on_edit.py → generate_ai_summary.py
    → AI_SUMMARY.md updated with new types/functions/LOC
```

No manual steps. The AI context is always current.

### 4. Dependency Graph (graphify)

[graphify](https://github.com/graphify/graphify) builds an AST-level dependency graph of the entire codebase. Instead of grepping for "where is X used?", you query:

```bash
graphify query "who calls processAudio"
graphify path "SenoApp" "TrackFreezer"
graphify update .    # re-index after changes (seconds, not minutes)
```

The graph is stored in `graphify-out/graph.json` and `GRAPH_REPORT.md`. Both the AI and the developer can query it without re-reading thousands of files.

### 5. Obsidian Memory Vault (Second Brain)

An Obsidian vault acts as the **persistent cross-session memory**. The vault has a dedicated project folder:

```
Obsidian/IA_Dev_Brain/
├── INDEX.md              ← navigation hub across all projects
├── LOG.md                ← chronological session journal (append-only)
├── SCHEMA.md             ← vault conventions
└── Seno/
    ├── _memory/
    │   └── memory.md     ← AI session memory (decisions, patterns, context)
    ├── decisions-log.md  ← architectural decisions with wikilinks
    └── standards-governance.md
```

**Session end protocol (mandatory):**
1. Update `Seno/_memory/memory.md` with session highlights
2. Append entry to `LOG.md`: `## YYYY-MM-DD — [Project] — 3-5 bullet summary`

This means the next session starts with full context — even weeks later, even on a different machine.

**Wikilink conventions:**
- Every note links to related notes via `[[wikilinks]]`
- Architectural decisions link to their ADR: `[[ADR-0002 Frozen Core]]`
- The `related:` frontmatter field is always populated

### 6. Claude Code Memory System

Claude Code persists cross-session memory in `~/.claude/projects/<project-key>/memory/`. The memory system has four types:

| Type | Content | When to save |
|---|---|---|
| `user` | Developer profile, expertise, preferences | When learning about the developer |
| `feedback` | Corrections and confirmations about approach | When the dev corrects or validates a pattern |
| `project` | Goals, deadlines, active work items | When learning about project state |
| `reference` | Pointers to external systems (Linear, Grafana) | When learning about external resources |

`MEMORY.md` is an index (≤ 200 lines) pointing to individual topic files. It's loaded automatically at session start.

### 7. Architecture Decision Records (ADRs)

Every non-obvious architectural decision gets an ADR in `docs/adr/NNNN-title.md`:

```markdown
# ADR-0002: Frozen Core — processAudio and run()
**Date**: 2026-05-07 | **Status**: Accepted

## Context
processAudio() is 2,133 LOC with CC ~100+. Any refactor risks audio dropouts.

## Decision
These two functions are never refactored without explicit architectural review.

## Consequences
Extractions target methods called FROM these functions, not the functions themselves.
```

The code references ADRs directly: `// See ADR-0002: Frozen Core`. This connects the why to the where.

### 8. Skills Ecosystem

Claude Code skills extend the assistant with domain-specific, project-aware commands:

| Skill | Purpose |
|---|---|
| `/verify-ai-docs` | Full 9-tier health check of this entire stack |
| `/verify-standards` | Quality governance scorecard (CI, docs, conventions) |
| `/audio-validate` | Real-time audio thread safety validator |
| `/realtime-audio` | Load RT constraints as context before audio work |
| `/cpp-coding-standards` | C++ Core Guidelines reference |
| `/clap-release` | Build and deploy CLAP audio plugin |

Skills are `.md` files in `.claude/skills/<name>/SKILL.md` — version-controlled with the project, available to every contributor.

### 9. The `verify-ai-docs` Skill

A 9-tier health check that verifies, auto-fixes, and reports the entire stack:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AI OPTIMIZATION STACK — HEALTH SCORECARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tier 1 — Core Scripts           5/5  ✅
Tier 2 — AI Documentation      15/15 ✅
Tier 3 — AI_SUMMARY Freshness  14/14 ✅
Tier 4 — Automation Chain       3/3  ✅
Tier 5 — graphify Graph         3/3  ✅
Tier 6 — Obsidian Memory Vault  5/5  ✅
Tier 7 — Claude Code Memory     3/3  ✅
Tier 8 — Project Quality Gates  5/5  ✅
Tier 9 — Skills Ecosystem       7/7  ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SCORE: 60/60 | Status: OPERATIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Auto-fixes: stale `AI_SUMMARY.md`, stale graphify graph, missing PostToolUse hook.  
Reports: missing `AI_CONTEXT.md` with ready-to-fill templates.  
Installs: prints step-by-step setup guide for new contributors.

---

## Quick Start

### For an existing project

```bash
# 1. Copy scripts into your project
cp -r tools/ai_docs/ your-project/tools/
cp -r skills/ your-project/.claude/

# 2. Configure machine-specific paths
cp tools/ai_docs/config.sh.example your-project/tools/ai_docs/config.sh
# Edit config.sh: set OBSIDIAN_VAULT, GRAPHIFY_BIN, CLAUDE_MEMORY_KEY

# 3. Register the PostToolUse hook in .claude/settings.json
# (see templates/settings_hook_example.json)

# 4. Write AI_CONTEXT.md for each major module
# (see templates/AI_CONTEXT_template.md)

# 5. Generate all AI_SUMMARY.md files
python tools/ai_docs/generate_all.py

# 6. Verify the full stack
# In Claude Code: /verify-ai-docs
```

### For a new machine / contributor

```bash
# 1. Clone the project (scripts are already committed)
git clone <your-project-repo>

# 2. Detect Python
bash tools/ai_docs/find_python.sh

# 3. Copy and edit the machine config
cp tools/ai_docs/config.sh.example tools/ai_docs/config.sh
# Set your Obsidian vault path, Python path, graphify binary

# 4. Register the hook (one-time)
# Add to .claude/settings.json → hooks.PostToolUse → Edit|Write:
# { "type": "command", "command": "bash /path/to/tools/ai_docs/run_hook.sh" }

# 5. Generate summaries
python tools/ai_docs/generate_all.py

# 6. Verify
# /verify-ai-docs → should show OPERATIONAL
```

---

## File Reference

### Auto-maintained (never edit manually)
| File | Updated by |
|---|---|
| `*/AI_SUMMARY.md` | PostToolUse hook on every `.cpp/.h/.rs` edit |
| `graphify-out/graph.json` | `graphify update .` (run manually or after big refactors) |

### Hand-written (stable, version-controlled)
| File | Content |
|---|---|
| `*/AI_CONTEXT.md` | Module purpose, thread model, constraints |
| `docs/REALTIME_RULES.md` | All RT thread constraints |
| `docs/adr/NNNN-*.md` | Architectural decision records |
| `CLAUDE.md` | Project-level AI instructions and conventions |

### Machine-specific (git-ignored)
| File | Content |
|---|---|
| `tools/ai_docs/config.sh` | Local paths: vault, Python, graphify, Claude memory |

---

## Obsidian Vault Structure

```
Obsidian/IA_Dev_Brain/
├── INDEX.md                  ← master navigation hub
├── LOG.md                    ← chronological session journal
├── SCHEMA.md                 ← frontmatter conventions, wikilink rules
│
├── Seno/                     ← one folder per project
│   ├── _memory/
│   │   └── memory.md         ← AI session memory (decisions, patterns)
│   ├── decisions-log.md      ← notable decisions with [[ADR]] wikilinks
│   ├── standards-governance.md
│   └── architecture/
│       └── track-b-refactor.md
│
├── OpenCode/                 ← another project
│   └── _memory/memory.md
│
└── _global/                  ← cross-project notes
    ├── professional-code-standards.md
    └── handoff/
```

### Frontmatter template (every vault note)
```yaml
---
project: seno          # seno | opencode | fulldesk | global
type: architecture     # architecture | decision | bug | reference | roadmap | log
tags: [seno, audio, track-b]
summary: "One sentence describing this note for future AI sessions (15-25 words)."
created: 2026-05-14
updated: 2026-05-14
related: [[INDEX]], [[Seno/CLAUDE]], [[ADR-0002]]
---
```

### Session recording (LOG.md format)
```markdown
## 2026-05-14 — Seno DAW — Track B Phase 19 group-track helpers

- Extracted `isTrackVisible`, `getTrackIndentLevel`, `getChildTracks`, `getAllDescendants`
- Added `toggleGroupCollapsed`, `setTrackParent`, propagate mute/solo to children
- −97 LOC net, SenoApp.cpp now 16 025 LOC (−73.8% cumul Track B)
- All 528 Rust tests + 114 GoogleTest passing, 0 warnings
- Next: [Phase 20 candidate TBD]
```

---

## Session End Protocol

At the end of every session (mandatory):

1. **Update project memory** (`Seno/_memory/memory.md`):
   - What was built/decided
   - Patterns discovered
   - Next steps

2. **Append to LOG.md**:
   ```
   ## YYYY-MM-DD — [Project] — Summary (3-5 bullets)
   ```

3. **Run `/verify-ai-docs`** to confirm everything is in sync.

This ensures the next session — even weeks later, even on a different machine — starts with full context.

---

## Customizing for Your Project

### 1. Module list
Edit the tracked modules list in `skills/verify-ai-docs/SKILL.md` (Step 0) to match your project's structure.

### 2. Machine paths
Copy `tools/ai_docs/config.sh.example` to `config.sh` and fill in:
- `GRAPHIFY_BIN` — path to graphify binary
- `OBSIDIAN_VAULT` — root of your Obsidian vault
- `OBSIDIAN_PROJECT_DIR` — subfolder for this project
- `CLAUDE_MEMORY_KEY` — subfolder name in `~/.claude/projects/`

### 3. AI_CONTEXT.md
Write one per module using `templates/AI_CONTEXT_template.md`. Focus on:
- What the module does (2-3 sentences)
- Which functions run on which thread
- What is forbidden here (alloc in RT, I/O in audio, etc.)
- One concrete usage example

### 4. REALTIME_RULES.md
Adapt `templates/REALTIME_RULES_template.md` to your constraints. Inject this file as context whenever working on performance-critical or multithreaded code.

---

## Why This Works

| Problem | Solution |
|---|---|
| AI forgets architecture between sessions | Obsidian LOG + Claude Code memory |
| AI proposes allocations in audio callback | REALTIME_RULES.md injected as context |
| AI doesn't know which thread a function runs on | AI_CONTEXT.md thread model table |
| AI suggests calling a function from wrong module | graphify query exposes call graph |
| AI_SUMMARY.md goes stale after code changes | PostToolUse hook auto-regenerates it |
| New contributor AI context from zero | `/verify-ai-docs` prints install guide |
| "What modules exist?" → grep | AI_SUMMARY.md LOC tables + graphify |

---

## Project Using This Stack

[**Seno DAW**](https://github.com/Rwanbt) — A professional audio/video/lighting DAW in C++17 + Rust with SDL3 + ImGui. 60k+ lines, fully refactored with this methodology. Track B reduced SenoApp.cpp from 62,002 LOC to ~16,000 LOC (−73.8%) while keeping all AI assistants fully oriented.

---

## License

MIT — use freely, adapt to your project, share improvements.

---

## Contributing

PRs welcome for:
- Additional language support (currently optimized for C++/Rust; Python/TypeScript templates welcome)
- graphify alternatives for other languages
- Additional skill templates
- Obsidian plugin integrations
