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
Engineering method (AGENTS.md)         ←  single canonical source, shared to every LLM
Per-module AI context files            ←  updated on every file edit
Dependency graph (graphify)            ←  re-indexed on demand
Domain rules (standalone)             ←  single file injected for critical code
Obsidian memory vault                  ←  persistent second brain across sessions
Claude Code memory                     ←  auto-generated session summaries
Skills ecosystem                       ←  domain-specific verification commands
Universal hooks                        ←  session memory load/save, LOC gate (any agent)
Anti-debt agent                        ←  deterministic tech-debt governance
PostToolUse hook                       ←  keeps everything in sync automatically
```

One command audits the entire stack: `/verify-ai-docs`. Transfer it to any
machine or LLM via **[PORTABILITY.md](PORTABILITY.md)**.

---

## Core design principle

A **module** is a directory containing `AI_CONTEXT.md`.
All tooling (summary generation, context assembly, hooks, metrics) is built around
this definition. Source files must be **direct siblings** of `AI_CONTEXT.md` —
subdirectory files are not scanned. This flat-module constraint is intentional:
it enforces high cohesion (one directory = one concern = one context) and keeps
the scanner simple and fast.

```
✅ Valid module structure        ❌ Invalid (nested files ignored)
my_module/                       my_module/
├── AI_CONTEXT.md                ├── AI_CONTEXT.md
├── token.rs                     ├── service/
├── session.rs                   │   └── token.rs   ← NOT scanned
└── utils.rs                     └── utils.rs
```

If a subdirectory grows large enough to need its own context, promote it to a
sub-module with its own `AI_CONTEXT.md`.

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

[graphify](https://github.com/safishamsi/graphify) builds an AST-level dependency graph for the entire codebase. Instead of grepping "where is X used?", you query:

```bash
graphify explain "processRequest"   # plain-language summary of a node + neighbors
graphify path "ModuleA" "ServiceB"  # shortest dependency path between two nodes
graphify update .                    # re-index after changes (seconds, not minutes)
```

The graph is stored in `graphify-out/graph.json` and `GRAPH_REPORT.md`. Both the AI and the developer can query it without re-reading thousands of files.

### 5. Obsidian Memory Vault (Second Brain)

An Obsidian vault serves as **persistent memory across sessions**. The
v4 contract places one folder per project under `projects/<slug>/`,
where `<slug>` is a lowercase kebab-case identifier registered in
`<vault>/_system/schemas/projects.json`:

```
<OBSIDIAN_VAULT>/
├── INDEX.md                    ← central navigation hub
├── LOG.md                      ← chronological session journal (append-only)
├── SCHEMA.md                   ← frontmatter and wikilink conventions
├── AGENTS.md                   ← vault-level agent entry, delegates to contract
│
├── projects/<slug>/            ← one folder per registered project
│   ├── INDEX.md                ← project navigation
│   ├── AGENTS.md               ← project-specific agent entry
│   ├── BOARD.md                ← generated status board (do not hand-edit)
│   ├── _memory/memory.md       ← AI session memory (decisions, patterns)
│   ├── decisions/              ← ADRs, one per file
│   ├── operations/sessions/    ← one file per session, written by SessionEnd hook
│   └── work/                   ← roadmaps, initiatives, runbooks
│
├── inbox/                      ← unchecked notes
├── archive/                    ← content that has been moved/superseded
└── _system/                    ← vault infrastructure (contract, tooling, schemas)
```

**v4 contract discovery (every harness):**
1. `OBSIDIAN_VAULT` — the vault root (CLI arg, then env var)
2. `OBSIDIAN_PROJECT_SLUG` — the active project slug (must match
   `[a-z0-9]+(?:-[a-z0-9]+)*`)
3. `<vault>/_system/schemas/projects.json` — project registry
4. `<vault>/_system/tooling/vault.py check` — canonical validator

The stack discovers the vault via the same protocol every harness
uses; the v4 contract is single-sourced in the vault, never copied
into harness configuration files.

**End-of-session protocol (mandatory, v4):**
1. The SessionEnd hook writes one immutable note to
   `projects/<slug>/operations/sessions/<session-id>.md`
2. It appends one line to `LOG.md` (a single append, never a rewrite)
3. The SessionStart hook loads `projects/<slug>/AGENTS.md`,
   `projects/<slug>/BOARD.md`, and the vault-level `AGENTS.md`

The next session will start with full context — even weeks later, even
on a different machine.

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

[gstack](https://github.com/garrytan/gstack) is a community collection of Claude Code skills created by Garry Tan (President of YC). It provides generic engineering skills available across **all** your projects, regardless of codebase:

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
Tier 1  — Core Scripts            8/8   ✅
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
  SCORE: 68/68 | Status: OPERATIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Auto-fixes: stale `AI_SUMMARY.md` files, outdated graphify graph, missing PostToolUse hook.  
Reports: missing `AI_CONTEXT.md` files with ready-to-fill templates.  
Installs: step-by-step installation guide for new contributors.

### 12. Metrics Snapshot (`tools/ai_docs/generate_metrics.py`)

Answers "how do we know this is working?" with objective, git-derived measurements written to `docs/METRICS.md`:

- **Coverage** — % of source directories that have an `AI_CONTEXT.md` (target ≥ 80%)
- **Freshness** — `AI_SUMMARY.md` up to date; `AI_CONTEXT.md` drift (stale docs where sources changed)
- **Knowledge base** — `KNOWN_FAILURE_PATTERNS.md` pattern count and ADR count (should grow over time)
- **Risk zones** — high-churn directories with no `AI_CONTEXT.md` (where AI errors are most likely)
- **Trend** — one append-only row per run, so coverage and risk are tracked over time

`/verify-ai-docs` regenerates this snapshot on every run.

### 13. Canonical Engineering Method (`AGENTS.md`)

The single source of the engineering rules every AI agent follows — the always-on
core (file/function size, error handling, naming, git, dependency direction) plus
the full senior-reflexes playbook (ADR/RFC, sanitizers, FFI, lock hierarchy, RT
telemetry, fuzz/property tests, supply-chain scans, perf budgets…) and the
codebase-analysis/routing strategy. Tool configs **reference** it (`@AGENTS.md`)
rather than copy it, so Claude Code, Cursor, Codex and MiniMax never diverge.
Read natively by Cursor/Codex; imported by Claude Code; inlined-and-synced for
agents without an import directive. See **[PORTABILITY.md](PORTABILITY.md)**.

### 14. Universal Hooks (`hooks/`)

Six cross-agent hooks that automate the methodology regardless of the tool:
session-start memory load, session-end save, PostToolUse AI-summary regeneration,
PreToolUse LOC gate, graphify inject, and a read-only-env permission guard. Each
ships per-agent install notes; secrets are read from the environment, never committed.

### 15. Anti-Debt Governance Agent (`stack/agents/anti-debt/`)

An LLM-agnostic technical-debt governance agent that counters the "ship the MVP"
bias: deterministic scanners + a Critic Engine (confidence tiers) + a SQLite
Knowledge Graph + governance skills, with adapters for Claude Code, MiniMax and
generic tools. Findings have a **deterministic identity** (stable across scans, so
dedup/history/calibration work), conform to JSON schemas, and separate deterministic
triage from LLM remediation plans. Linked into each agent via `scripts/setup-agents.sh`.

### 16. Portable, Non-Destructive Updates (`UPDATING.md`)

The whole stack transfers to a new machine or LLM via one clone + `setup-agents.sh`,
and stays current without destroying anyone's personalization. `stack-update-check.sh`
detects upstream changes in the shared *clone* (read-only); `/stack-upgrade` fast-forwards
it. Because personal configs *reference* the shared files, a `git pull` updates the method
for everyone while each user keeps their customizations. For inlined targets (e.g.
MiniMax), `sync_inlined_method.py` refreshes a managed block.

A project you **installed** into is a different surface, updated by `ainative update`
with recorded per-file ownership. See **[UPDATING.md](UPDATING.md)** for both.

### 17. Distribution & Lifecycle (`ainative`)

One CLI owns installation, profile choice, update and removal, and it records what
it wrote so it can undo it:

```bash
ainative init                     # choose Standard or Verified
ainative status                   # what is installed, and its health
ainative profile switch verified  # reversible, non-destructive, both ways
ainative update check             # detection is automatic; application never is
ainative uninstall                # removes the stack, keeps your work
```

Every managed file carries the SHA-256 it had when the stack wrote it, so an update
never overwrites your edit and an uninstall never deletes it. Mutations are
transactional (backup → apply → verify → commit state *last*), so an interruption
leaves the old valid state or the new one, never a half-installed project.
See **[docs/DISTRIBUTION-LIFECYCLE.md](docs/DISTRIBUTION-LIFECYCLE.md)** and
[ADR-0009](docs/adr/0009-distribution-profiles-and-lifecycle-ownership.md).

---

## Which profile should I choose?

```
AI Native Dev Stack
        │
        ├── Standard    context · memory · skills · hooks · adapters · AI docs
        │
        └── Verified    Standard + Work Contracts · verification · convergence
```

### Standard

Context, memory, skills and AI-native tooling. **Recommended for learning,
personal development and normal AI-assisted work** — students, individual
developers, fast setup.

### Verified

Standard **plus** governed Work Contracts and deterministic verification.
**Recommended for production, teams and autonomous agents** — critical code and
auditability.

> **Standard optimizes how AI works with the project.**
> **Verified additionally governs and deterministically verifies declared work.**

Verified extends Standard; Standard never depends on Verified. You can move
between them at any time in either direction, and moving down to Standard
preserves your Verified history as dormant state rather than deleting it.

```bash
ainative init --profile standard      # non-interactive
ainative init --profile verified
ainative profile switch standard      # keeps trust, contracts and evidence
ainative profile switch verified      # reactivates them
```

---

## The Verified Work Plane

A deterministic gate between an agent claiming work is done and the project
believing it. It decides convergence from committed contracts and executed
verifications — never from narrative, and never from anything the caller hands
in.

    pip install .
    ainative trust bootstrap --repo . --approval-root root.json --policy policy.json --by "you"
    ainative work admit .ai-native/work/w1 --repo . --by "you" --artifact ...
    ainative work new   .ai-native/work/w1 --artifact ...
    ainative converge   --work .ai-native/work/w1 --repo .

Exit codes: 0 CONVERGED, 1 NOT_CONVERGED, 2 INVALID, 3 INTERNAL_ERROR.

Its authority model was closed by external adversarial review (P0 = 0, P1 = 0)
and is frozen. Genesis trust is a privileged ceremony the runtime cannot
verify, so **bootstrap trust before a controlled agent has repository access**
— that is a deployment requirement, not a detail. See ADR-0006.

Full documentation, empirical results and known limitations:
[docs/VERIFIED-WORK-PLANE.md](docs/VERIFIED-WORK-PLANE.md).

## Quick Start

### For an existing project

```bash
# 1. Install the CLI (once), then choose a profile in your project
pip install git+https://github.com/Rwanbt/ai-native-dev-stack.git
cd your-project
ainative init                          # asks Standard or Verified
#   or, non-interactively:
ainative init --profile standard
ainative init --profile standard --dry-run   # see the plan first, change nothing

# No pip yet? The bootstrap does the same thing from a clone:
#   bash install.sh --profile standard        (Linux / macOS / Git Bash)
#   pwsh -File install.ps1 -Profile standard  (Windows)

# 2. Configure machine-specific paths (the installer seeds this file and
#    never overwrites it afterwards)
# Edit tools/ai_docs/config.sh: OBSIDIAN_VAULT, GRAPHIFY_BIN, CLAUDE_MEMORY_KEY

# 3. Register the PostToolUse hook in .claude/settings.json
# (see .ai-native/templates/settings_hook_example.json)

# 4. Write AI_CONTEXT.md for each major module
# (see .ai-native/templates/AI_CONTEXT_template.md)

# 5. Generate all AI_SUMMARY.md files
python tools/ai_docs/generate_all.py

# 6. Check the install, then verify the full stack
ainative status
#    /verify-ai-docs   — in any agent that loaded the skills
#                        (Claude Code, Codex, OpenCode, Cursor)
```

Already installed the old way, before the lifecycle existed? Nothing to migrate
by hand: `ainative init` detects the existing files and adopts them without
overwriting anything you edited.

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

### Whole-stack transfer (method + hooks + agents, any LLM)

The steps above set up the per-project AI-docs stack. To transfer the **full
method** to a new machine or wire a new AI agent (Claude Code, MiniMax/Mavis,
Cursor, Codex) to the same rules, hooks, and the anti-debt agent:

```bash
# Install rules, skills and agents into every detected AI CLI
# (idempotent; one Python implementation, same behaviour on every OS)
bash scripts/setup-agents.sh                          # Linux / macOS / Git Bash
pwsh -NoProfile -File scripts/setup-agents.ps1        # Windows, no Git Bash needed
python scripts/install_agents.py                      # any OS, direct

# Verify, or preview without writing:
python scripts/install_agents.py --check
python scripts/install_agents.py --dry-run

# Then wire the engineering method (@AGENTS.md include) + hooks per agent:
#   → see PORTABILITY.md
```

Skills are installed into every agent root the stack knows about — Claude Code
(`~/.claude/skills`) and the cross-CLI `~/.agents/skills` used by Codex,
OpenCode and Cursor — as links, not copies, so a `git pull` updates every CLI
at once.

The single source of the engineering method is [`AGENTS.md`](AGENTS.md) — every
tool config references it instead of re-stating the rules, so the configs never
diverge. Full guide: **[PORTABILITY.md](PORTABILITY.md)**.

**Staying up to date** (gstack-style, non-destructive): `bash scripts/stack-update-check.sh`
detects upstream changes (read-only); `/stack-upgrade` (or `bash scripts/stack-upgrade.sh`)
fast-forwards the shared clone without ever touching your personalized configs.
Because configs *reference* `AGENTS.md` rather than copy it, a `git pull` updates
the method for everyone while each user keeps their customizations. Full model:
**[UPDATING.md](UPDATING.md)**.

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
| `docs/METRICS.md` | `generate_metrics.py` (run by `/verify-ai-docs`) |
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
- `OBSIDIAN_PROJECT_SLUG` — canonical kebab-case slug for this project (for example, `ai-native-dev-stack`)
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

## v4 vault integration

The stack targets the v4 vault contract without copying it: every
harness (Claude Code, Codex, OpenCode, Cursor, Gemini, Mavis) discovers
the same vault, validates the same way, and refuses to write into a
vault that fails the contract.

| Concept | How the stack handles it |
|---|---|
| Vault discovery | `--vault` argument, then `$OBSIDIAN_VAULT`. Never hard-coded. |
| Project slug | `--project-slug` argument, then `$OBSIDIAN_PROJECT_SLUG`, then validated against the v4 grammar `[a-z0-9]+(?:-[a-z0-9]+)*`. |
| v4 detection | The protocol checks for `_system/schemas/projects.json`, `_system/tooling/vault.py`, and the root `AGENTS.md`. |
| Validation | The stack calls `<vault>/_system/tooling/vault.py check` (with `lint` fallback) — it does not re-implement the schema. |
| Maintenance lock | A `.git/maintenance.lock` sentinel halts the sync. Remove it only when the orchestrator is done. |
| Per-harness block | `scripts/install_agents.py` writes a "Vault governance" block to Claude (`~/.claude/CLAUDE.md`), Codex, OpenCode, Cursor (`~/.cursor/rules/ai-native-dev-stack.mdc`), Gemini (`~/.gemini/GEMINI.md`) and Mavis. |
| Boards | The SessionEnd hook never writes to `BOARD.md` — boards are generated navigation views; canonical cards hold status. |
| Sync | `scripts/vault_sync.py` runs the v4 validator before staging, preserves secret scan, single-writer, divergence detection and remote SHA verification. |
| Check / rollback | `python scripts/install_agents.py --check --vault <vault> --project-slug <slug>` reports block state; `python scripts/vault_sync.py --no-validator-check` is the *only* legacy opt-in. |

### Install, check, rollback, uninstall

```bash
# Install: method + vault governance block into every supported harness
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug>

# Check: 0 changes, 0 issues on a clean install
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --check

# Rollback: remove the "Vault governance" block from every harness.
# The shared engineering method block is preserved.
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --no-vault-block

# Restart every AI client so it reloads the global rules.
```

### What the v4 contract is NOT

The stack does not:

- Hard-code any vault path. There is no `D:\Documents\...` constant
  anywhere; the user always supplies the vault, and an unconfigured
  vault is a clear error, not a default.
- Copy the v4 contract. Every block is a pointer to the vault's own
  `AGENTS.md`; the contract text lives in one place only.
- Write into the vault during a normal install. The installer writes
  to user-level harness directories (`~/.claude/`, `~/.codex/`,
  `~/.config/opencode/`, `~/.cursor/rules/`, `~/.gemini/`, `~/.mavis/...`); the vault is read-only
  from the stack's perspective.

### Local write, commit, push, publish — four distinct actions

The stack never conflates them. A "push" is always a separate step
from a "write" or a "commit", and only `scripts/vault_sync.py` does
the former two. The hooks and installers only write locally; the
sync is the only path to the remote, and it enforces the v4 contract
on the way.
