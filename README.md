<div align="center">

<img src="ai_native_dev_stack.png" alt="banner_ai_native_dev_stack" >

English · [Français](README.fr.md)

# AI-Native Dev Stack

> A complete methodology and toolbox for making any large codebase immediately understandable by AI assistants — with automatic maintenance so context never goes stale.

[![CI](https://github.com/Rwanbt/ai-native-dev-stack/actions/workflows/ci.yml/badge.svg)](https://github.com/Rwanbt/ai-native-dev-stack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Works with Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-green)](https://claude.ai/code)
[![Claude Code skill](https://img.shields.io/badge/skill-verify--ai--docs-purple)](skills/verify-ai-docs/SKILL.md)

</div>

---

## The Problem

Large codebases (60k+ lines, multi-language, multi-threaded) saturate AI context windows. Without structure, every session starts from zero: the AI hallucinates the architecture, ignores real-time constraints, and proposes solutions that break the threading model.

The usual workarounds (pasting files into context, writing long prompts) don't scale. They are manual, they go stale, and they spend tokens on noise rather than signal.

## The Solution

A **self-maintained AI optimization stack** — a set of structured documents, scripts, and hooks that keeps the AI perpetually oriented without human intervention:

```
Per-module AI context files            ←  updated on every file edit
Dependency graph (graphify)            ←  re-indexed on demand
Domain rules (standalone)             ←  single file injected for critical code
Obsidian memory vault                  ←  persistent second brain across sessions
Claude Code memory                     ←  auto-generated session summaries
Skills ecosystem                       ←  domain-specific verification commands
PostToolUse hook                       ←  keeps everything in sync automatically
```

One command audits the entire stack: `/verify-ai-docs`

---

## Stack Components

### 1. Per-Module AI Context (`AI_CONTEXT.md`)

Each source module receives a hand-written `AI_CONTEXT.md` that captures what no README ever documents: **threading model, forbidden patterns, non-obvious constraints, common call patterns**.

```
src/modules/auth/
├── AI_CONTEXT.md      ← hand-written: purpose, thread model, constraints
├── AI_SUMMARY.md      ← auto-generated: public types, functions, LOC table
├── AuthService.ts
├── TokenManager.ts
└── ...
```

**`AI_CONTEXT.md` covers:**
- Module purpose (2-3 sentences)
- Threading model table (which function runs on which thread)
- Constraints (what is allowed / forbidden here)
- **Common failure modes** — the 3-5 most dangerous bugs when used incorrectly
- **Hot files** — the 2-4 files with the most dangerous invariants or highest churn rate
- Common usage patterns with code examples
- Cross-references to related ADRs and modules

**`AI_SUMMARY.md` is auto-generated** from source headers on every edit via a PostToolUse hook. It always reflects the current public API: types, functions, LOC counts with size alerts.

### 2. Domain Rules (`docs/REALTIME_RULES.md` or equivalent)

A standalone document covering all constraints for critical code: real-time threads, security, performance, network protocols, etc. Injected as context when working on code adjacent to those constraints.

Typical sections:
- Threading model diagram
- Absolute callback constraints (zero alloc, zero blocking, zero exceptions)
- Lock-free data transfer patterns
- Frozen zones (functions never refactored without architectural review)
- DSP rules / domain-specific rules

### 3. Automatic Maintenance (PostToolUse Hook)

A Claude Code `PostToolUse` hook fires after every `Edit` or `Write` on a source file. It detects which module was modified and regenerates that module's `AI_SUMMARY.md` in under a second.

```
Edit SessionManager.cpp
    → hook fires → update_on_edit.py → generate_ai_summary.py
    → AI_SUMMARY.md updated with new types/functions/LOC
```

Zero manual steps. AI context is always current.

### 4. Dependency Graph (graphify)

[graphify](https://github.com/graphify/graphify) builds an AST-level dependency graph for the entire codebase. Instead of grepping "where is X used?", you query:

```bash
graphify query "who calls processRequest"
graphify path "ModuleA" "ServiceB"
graphify update .    # re-index after changes (seconds, not minutes)
```

The graph is stored in `graphify-out/graph.json` and `GRAPH_REPORT.md`. Both the AI and the developer can query it without re-reading thousands of files.

### 5. Obsidian Memory Vault (Second Brain)

An Obsidian vault serves as **persistent memory across sessions**. The vault has one dedicated folder per project:

```
Obsidian/MyVault/
├── INDEX.md                  ← central navigation hub
├── LOG.md                    ← chronological session journal (append-only)
├── SCHEMA.md                 ← frontmatter and wikilink conventions
│
├── ProjectA/                 ← one folder per project
│   ├── _memory/
│   │   └── memory.md         ← AI session memory (decisions, patterns)
│   ├── decisions-log.md      ← notable decisions with [[wikilinks]] to ADRs
│   └── architecture/
│       └── module-notes.md
│
├── ProjectB/                 ← another project
│   └── _memory/memory.md
│
└── _global/                  ← cross-project notes
    ├── professional-code-standards.md
    └── handoff/
```

**End-of-session protocol (mandatory):**
1. Update `ProjectA/_memory/memory.md` with the session's key findings
2. Append an entry to `LOG.md`: `## YYYY-MM-DD — [Project] — 3-5 bullet summary`

The next session will start with full context — even weeks later, even on a different machine.

**Wikilink conventions:**
- Every note links to related notes via `[[wikilinks]]`
- Architectural decisions link to their ADR: `[[ADR-0004 Extract Service Pattern]]`
- The `related:` frontmatter field is always populated

### 6. Claude Code Memory

Claude Code persists cross-session memory in `~/.claude/projects/<project-key>/memory/`. Four memory types:

| Type | Content | When to record |
|---|---|---|
| `user` | Developer profile, expertise, preferences | When learning about the developer |
| `feedback` | Corrections and approach confirmations | When the dev corrects or validates a pattern |
| `project` | Goals, deadlines, work in progress | When learning the project state |
| `reference` | Pointers to external systems (Linear, Grafana, Notion) | When discovering external resources |

`MEMORY.md` is an index (≤ 200 lines) pointing to individual topic files. It is loaded automatically at session start.

### 7. ADRs — Architecture Decision Records (`docs/adr/`)

Every non-trivial architectural decision gets an ADR in `docs/adr/NNNN-title.md`:

```markdown
# ADR-0004: Host struct pattern — service extraction
**Date**: 2026-05-07 | **Status**: Accepted

## Context
The main file (18,000 LOC) concentrates too many responsibilities.

## Decision
Extract each domain into a dedicated service with a Host struct
passed as a parameter (no singleton, explicit injection).

## Consequences
Services testable in isolation. Zero global state. Traceable ownership.
```

Code references ADRs directly: `// See ADR-0004: Host struct pattern`. This connects the *why* to the *where*.

### 8. Known Failure Patterns (`docs/KNOWN_FAILURE_PATTERNS.md`)

A hand-written, append-only catalog of the most dangerous bugs in the codebase — organized by category (threading, FFI, serialization, UI, etc.). Each entry: symptom, root cause, detection method, prevention.

This is the **institutional memory of pain**: every post-mortem that identifies a systemic problem adds an entry. New contributors read it before touching sensitive areas.

```markdown
## 1. Real-Time Thread Violations

### 1.1 Memory Allocation in the Audio Callback
**Symptom**: Random crackles under load.
**Cause**: std::vector::push_back (resize) inside the callback.
**Detection**: malloc wrapper with _CrtSetAllocHook in debug builds.
**Prevention**: Pre-allocate all buffers at startup.
```

### 9. Context Assembler (`tools/ai_docs/assemble_context.py`)

The **Context Assembler** generates a single, focused briefing document for any source file:

```bash
python tools/ai_docs/assemble_context.py src/services/payment/PaymentGateway.cpp
# Output includes:
# - Module AI_CONTEXT.md (purpose, thread model, constraints, failure modes)
# - AI_SUMMARY.md (public API snapshot)
# - docs/REALTIME_RULES.md (if RT constraints detected)
# - Referenced ADRs (from the ## See also section)
# - KNOWN_FAILURE_PATTERNS.md (if present)
# - graphify dependency path (if binary available)
# - Claude Code MEMORY.md excerpt (first 50 lines)
```

Replaces the need to manually collect context before working on a module. The AI receives all relevant information in a single assembled document.

### 10. Skills Ecosystem

Claude Code skills extend the assistant with domain-specific, project-aware commands.

#### Project-specific skills (this stack)

| Skill | Purpose |
|---|---|
| `/verify-ai-docs` | Full stack health check (10 tiers) |
| `/verify-standards` | Quality scorecard — CI, docs, conventions, metrics |

Skills are `.md` files in `.claude/skills/<name>/SKILL.md` — versioned with the project, available to every contributor.

#### gstack — Global Engineering Skills

[gstack](https://github.com/garrytan/gstack) is a community collection of Claude Code skills created by Gary Tan (President of YC). It provides generic engineering skills available across **all** your projects, regardless of codebase:

| Skill | Purpose |
|---|---|
| `/investigate` | Root-cause debugging in 4 guided phases |
| `/review` | Pre-landing code review with auto-fixes |
| `/health` | Quick health dashboard (tests, lint, build) |
| `/plan-eng-review` | Architecture review before implementation |
| `/plan-ceo-review` | Strategic scope and ambition review |
| `/office-hours` | Product brainstorming, YC Office Hours style |
| `/qa` | Systematic QA with headless browser + fixes |
| `/ship` | Release engineering — tests, PR, push |
| `/ci-heal` | Automatically repairs broken GitHub Actions CI |
| `/codex` | Second opinion via Codex CLI (adversarial mode) |
| `/context-save` / `/context-restore` | Progress checkpoint across sessions |
| `/document-release` | Post-ship documentation update |

**Integration with this stack:** gstack and project-specific skills are **complementary**. gstack handles the general engineering workflow (`/review`, `/ship`, `/qa`); project-specific skills handle internal codebase quality (`/verify-ai-docs`, `/verify-standards`). Both coexist in `~/.claude/skills/`.

Installation: see the gstack documentation on GitHub.

### 11. The `/verify-ai-docs` Skill

A 10-tier health check that audits, auto-fixes, and reports the state of the entire stack:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AI OPTIMIZATION STACK — HEALTH SCORECARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tier 1  — Core Scripts            6/6   ✅
Tier 2  — AI Documentation       16/16  ✅  ← includes coverage check
Tier 3  — AI_SUMMARY Freshness   14/14  ✅
Tier 4  — Automation Chain        3/3   ✅
Tier 5  — graphify Graph          3/3   ✅
Tier 6  — Obsidian Memory Vault   5/5   ✅
Tier 7  — Claude Code Memory      3/3   ✅
Tier 8  — Project Quality Gates   6/6   ✅  ← includes KFP
Tier 9  — Skills Ecosystem        7/7   ✅
Tier 10 — Cognitive Contract      3/3   ✅  ← failure modes · KFP · assembler
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SCORE: 66/66 | Status: OPERATIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Auto-fixes: stale `AI_SUMMARY.md` files, outdated graphify graph, missing PostToolUse hook.  
Reports: missing `AI_CONTEXT.md` files with ready-to-fill templates.  
Installs: step-by-step installation guide for new contributors.

---

## Quick Start

### For an existing project

```bash
# 1. Copy scripts into your project
cp -r tools/ai_docs/ your-project/tools/
cp -r skills/ your-project/.claude/

# 2. Configure machine-specific paths
cp tools/ai_docs/config.sh.example your-project/tools/ai_docs/config.sh
# Edit config.sh: fill in OBSIDIAN_VAULT, GRAPHIFY_BIN, CLAUDE_MEMORY_KEY

# 3. Register the PostToolUse hook in .claude/settings.json
# (see templates/settings_hook_example.json)

# 4. Write AI_CONTEXT.md for each major module
# (see templates/AI_CONTEXT_template.md)

# 5. Generate all AI_SUMMARY.md files
python tools/ai_docs/generate_all.py

# 6. Verify the full stack
# In Claude Code: /verify-ai-docs
```

### For a new machine / new contributor

```bash
# 1. Clone the project (scripts are already committed)
git clone <project-repo>

# 2. Detect Python
bash tools/ai_docs/find_python.sh

# 3. Copy and edit the machine config
cp tools/ai_docs/config.sh.example tools/ai_docs/config.sh
# Fill in Obsidian vault path, Python path, graphify binary

# 4. Register the hook (once)
# Add to .claude/settings.json → hooks.PostToolUse → Edit|Write:
# { "type": "command", "command": "bash /absolute-path/tools/ai_docs/run_hook.sh" }

# 5. Generate summaries
python tools/ai_docs/generate_all.py

# 6. Verify → /verify-ai-docs should display OPERATIONAL
```

---

## Quality Standards — AI Optimization and Human Readability

This methodology optimizes simultaneously for **two audiences**: the AI (context window, signal-to-noise ratio, accuracy) and humans (maintainability, code review, onboarding). The same rules serve both.

### File Size

| Threshold | Action |
|---|---|
| ≤ 500 LOC | Green zone — healthy file |
| > 500 LOC (new file) | Flag it, propose decomposition |
| > 800 LOC (modified file) | Propose extracting secondary responsibilities |
| > 1,500 LOC | **Refactoring required before any addition** |

**Why it helps the AI:** A 300-LOC file fits in a single context call. A 2,000-LOC file requires round-trips or truncation — with hallucination risk on the unseen parts.

**Why it helps humans:** Industrial SonarQube rule. A file you can't read entirely in 5 minutes can't be reviewed properly.

### Function Size and Complexity

| Metric | Target | Warning | Blocking |
|---|---|---|---|
| LOC per function | ≤ 50 | > 100 | > 200 |
| Cyclomatic complexity | ≤ 10 | > 15 | > 25 |
| Nesting depth | ≤ 3 | 4 | > 4 |

**Why it helps the AI:** A 50-LOC function can be understood in a single context block. A 500-LOC function creates uncertainty: the AI can't keep all branches in mind simultaneously.

### Comment Policy — WHY, never WHAT

```cpp
// ❌ Describes WHAT the code does (the code is already readable)
// Iterate over all tracks and mute them
for (auto& track : tracks) { track.muted = true; }

// ✅ Documents WHY this constraint exists
// Must process in reverse order — forward pass causes PDC drift (ADR-0007)
for (auto it = tracks.rbegin(); it != tracks.rend(); ++it) { ... }
```

**Why it helps the AI:** WHY comments are high-density information — they explain constraints that cannot be inferred from the code. WHAT comments are pure noise for the AI (which can read the code itself).

### Explicit Naming

- `processAudioFrame()` > `process()` — unambiguous about the domain
- `userEmailAddress` > `email` — unambiguous about type and scope
- `MAX_RETRY_COUNT` > `MAX` — unambiguous about usage
- No cryptic abbreviations: `idx` → `index`, `cnt` → `count`, `mgr` → `manager`

**Why it helps the AI:** Explicit names eliminate costly ambiguity. The AI doesn't have to infer what `process()` does in an audio/network/data context.

### Zero Dead Code

Delete immediately, never comment out. A commented-out block is more dangerous than deletion: it pollutes the AI's context with code that is no longer executed.

```bash
# Detection
grep -r "TODO\|FIXME\|HACK\|XXX" src/   # each occurrence = ticket or deletion
```

**Why it helps the AI:** Every line of dead code consumes tokens and can mislead the AI about what is active. Git allows recovering any deleted code via `git log -S "function_name"`.

### Single Responsibility (SRP)

Before writing into an existing file, three questions:
1. **"Does this code truly belong here?"** — if not, create the appropriate file
2. **"Am I adding a second responsibility?"** — if so, separate file
3. **"Is this helper reusable elsewhere?"** — if so, extract into a shared module

**Why it helps the AI:** One file = one responsibility = one clear context. The AI can reason about a module without having to understand interleaved concerns.

### Zero Global State — Singletons Included

**Forbidden**: `static T g_xxx` in a `.cpp` (or unjustified `lazy_static` in Rust). **Also forbidden**: singletons via `getInstance()` — they are disguised globals.

Prefer explicit dependency injection: parameter, class member with identifiable owner.

**Why it helps the AI:** Global state makes non-local reasoning impossible. The AI cannot analyze a function without tracing all globals it might modify.

### Error Handling — Never Silent

- **Rust**: `unwrap()` and `expect()` forbidden in production except for proven invariants
- **C++**: Never an empty `catch(...)` — always handle or re-throw
- **TypeScript**: Never an empty `catch (e) {}` — log or propagate

**Why it helps the AI:** Silent errors create inconsistent states that the AI will diagnose as bugs in healthy code. Explicit errors give the AI clear signals.

### PR Size

≤ 400 LOC changed per PR (additions + deletions). Beyond that, the reviewer cannot maintain concentration — and neither can the AI.

**Why it helps the AI:** A 400-LOC PR can be analyzed in one pass. A 4,000-LOC PR requires multiple passes with loss of coherence.

### Documentation Proportional to Project Size

| Project threshold | Required documents |
|---|---|
| > 10 source files | `CLAUDE.md` — AI instructions + conventions |
| > 3,000 total LOC | `ARCHITECTURE.md` — thread model, data flow, ownership |
| > 5,000 LOC | `CONTRIBUTING.md` — conventions, onboarding, PR checklist |
| Complex module | `docs/adr/` — architectural decisions |

**Why it helps the AI:** `CLAUDE.md` is loaded automatically in every session. `ARCHITECTURE.md` prevents hallucinations about the global design. ADRs explain counter-intuitive decisions.

### Commit Conventions (Conventional Commits)

```
feat: add JWT token refresh mechanism
fix: prevent double-trigger in event handler
refactor: extract PaymentService from AppController
perf: pre-allocate audio buffers at startup
docs: add threading constraints to AudioModule AI_CONTEXT
```

**Why it helps the AI:** The AI can scan `git log` and immediately understand history without reading every diff. Atomic, conventional commits allow finding the introduction of a bug with `git bisect` in minutes.

---

## File Reference

### Auto-maintained (never edit manually)
| File | Updated by |
|---|---|
| `*/AI_SUMMARY.md` | PostToolUse hook on every source file edit |
| `graphify-out/graph.json` | `graphify update .` (manually or after large refactors) |

### Hand-written (stable, versioned)
| File | Content |
|---|---|
| `*/AI_CONTEXT.md` | Purpose, thread model, constraints, failure modes |
| `docs/REALTIME_RULES.md` | Real-time thread constraints (or domain equivalent) |
| `docs/KNOWN_FAILURE_PATTERNS.md` | Catalog of systemic bugs |
| `docs/adr/NNNN-*.md` | Architecture decisions |
| `CLAUDE.md` | AI instructions at the project level and conventions |

### Machine-specific (git-ignored)
| File | Content |
|---|---|
| `tools/ai_docs/config.sh` | Local paths: Obsidian vault, Python, graphify, Claude memory |

---

## Obsidian Vault Structure

```
Obsidian/MyVault/
├── INDEX.md                  ← central navigation hub
├── LOG.md                    ← chronological session journal
├── SCHEMA.md                 ← frontmatter and wikilink conventions
│
├── ProjectA/                 ← one folder per project
│   ├── _memory/
│   │   └── memory.md         ← AI session memory (decisions, patterns)
│   ├── decisions-log.md      ← notable decisions with [[wikilinks]] to ADRs
│   └── architecture/
│       └── notes.md
│
├── ProjectB/                 ← another project
│   └── _memory/memory.md
│
└── _global/                  ← cross-project notes
    ├── professional-code-standards.md
    └── handoff/
```

### Frontmatter Template (every vault note)

```yaml
---
project: project-a         # project identifier
type: architecture         # architecture | decision | bug | reference | roadmap | log
tags: [project-a, services, refactor]
summary: "One sentence describing this note for future AI sessions (15-25 words)."
created: 2026-05-14
updated: 2026-05-14
related: [[INDEX]], [[ProjectA/CLAUDE]], [[ADR-0004]]
---
```

### Session Recording Format (`LOG.md`)

```markdown
## 2026-05-14 — Project A — Authentication service extraction

- Extracted `TokenValidator`, `SessionManager`, `RefreshHandler` from `AppController`
- −240 LOC net, AppController.ts goes from 1,850 to 1,610 LOC
- All tests pass, 0 lint warnings
- Pattern: Host struct injected as parameter — no singleton
- Next: extract `PermissionChecker` (~180 LOC estimated)
```

---

## End-of-Session Protocol

At the end of every session (mandatory):

1. **Update project memory** (`ProjectA/_memory/memory.md`):
   - What was built / decided
   - Patterns discovered
   - Next steps

2. **Append to `LOG.md`**:
   ```
   ## YYYY-MM-DD — [Project] — Summary (3-5 bullets)
   ```

3. **Run `/verify-ai-docs`** to confirm everything is in sync.

The next session — even weeks later, even on a different machine — will start with full context.

---

## Adapting to Your Project

### 1. Module List
Auto-discovery is based on the presence of `AI_CONTEXT.md`. No hardcoded list to maintain — simply place an `AI_CONTEXT.md` in each module directory.

### 2. Machine Paths
Copy `tools/ai_docs/config.sh.example` to `config.sh` and fill in:
- `GRAPHIFY_BIN` — path to the graphify binary
- `OBSIDIAN_VAULT` — root of your Obsidian vault
- `OBSIDIAN_PROJECT_DIR` — subfolder for this project
- `CLAUDE_MEMORY_KEY` — subfolder name in `~/.claude/projects/`

### 3. `AI_CONTEXT.md`
Write one file per module using `templates/AI_CONTEXT_template.md`. Focus on:
- What the module does (2-3 sentences)
- Which functions run on which thread
- What is forbidden here
- The 3-5 most common bugs when used incorrectly
- A concrete usage example

### 4. `KNOWN_FAILURE_PATTERNS.md`
Create `docs/KNOWN_FAILURE_PATTERNS.md` and feed it after every post-mortem. Format:
```markdown
### N.N — Short title
**Symptom**: What the developer observes.
**Cause**: Why it happens.
**Detection**: How to detect it (tool, assert, log).
**Prevention**: Rule to follow to never fall into it again.
```

### 5. Domain Rules
Adapt or create a `docs/REALTIME_RULES.md` file (or `SECURITY_RULES.md`, `PROTOCOL_RULES.md`...) according to your domain's constraints. The name doesn't matter — the context assembler injects it when RT constraint keywords are detected in `AI_CONTEXT.md`.

---

## Why It Works

| Problem | Solution |
|---|---|
| AI forgets architecture between sessions | Obsidian LOG + Claude Code memory |
| AI proposes code forbidden in a critical zone | Domain rules injected as context |
| AI doesn't know which thread runs which function | Thread model table in `AI_CONTEXT.md` |
| AI suggests calling a function from the wrong module | `graphify query` exposes the call graph |
| `AI_SUMMARY.md` goes stale after changes | PostToolUse hook regenerates it automatically |
| New contributor → zero AI context | `/verify-ai-docs` prints the installation guide |
| "What modules exist?" → grep | LOC tables in `AI_SUMMARY.md` + graphify |
| Same systemic bugs repeating | `KNOWN_FAILURE_PATTERNS.md` — institutional memory |
| File too large → AI hallucinations | LOC standards + mandatory refactoring at 1,500 |

---

## License

MIT — free to use, adapt to your project, contributions welcome.

---

## Contributing

PRs welcome for:
- Additional language support (optimized for C++/Rust/TypeScript; Python/Go templates welcome)
- graphify alternatives for other languages
- Additional skill templates
- Obsidian integrations
- README translations
