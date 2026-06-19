# Portability — Transfer the full stack to a new machine or LLM

This guide makes the whole AI-Native Dev Stack reproducible: clone the repo and
wire each AI agent (Claude Code, MiniMax/Mavis, Cursor, Codex, …) to the same
engineering method, hooks, and agents. Nothing here depends on a specific
machine except the few values explicitly listed as machine-local.

## The 3-layer model (why some things live in the repo and some don't)

Per-tool configs mix three natures that must not travel together:

| Layer | What | Where it lives | Shared? |
|---|---|---|---|
| **1 — Engineering method** | The universal rules + senior reflexes | [`AGENTS.md`](AGENTS.md) (this repo) | ✅ canonical, shared to every agent |
| **2 — Tool mechanics** | Skills/commands of a given tool (gstack, graphify, MCP wiring) | Per-agent appendix (this repo's adapters + each tool's config) | ⚠️ per-agent |
| **3 — Personal / machine** | Vault paths, project list, machine PATH, "answer in French", wikilink rules | The agent's own config file (`~/.claude/CLAUDE.md`, Mavis `agent.md`) | ❌ never shared |

**Rule:** Layer 1 has exactly one owner — `AGENTS.md`. Every tool config
*references* it (`@AGENTS.md` include) instead of re-stating the rules. That is
what keeps the three configs from diverging. If you copy the rules into a tool
config by hand, you have just created a fork that will rot.

## What is in the repo (transferable) vs machine-local

| In the repo (clone = you have it) | Machine-local (set up once per machine) |
|---|---|
| `AGENTS.md` — the complete method (Layer 1) | `~/.claude/CLAUDE.md` — Layer 3 + `@AGENTS.md` include |
| `routing-guide.md` — analysis/orchestration routing | Mavis `~/.mavis/agents/mavis/agent.md` — Layer 3 + method ref |
| `hooks/` — universal hooks + per-agent install notes | Obsidian vault (`config.sh` paths, API key in env) |
| `scripts/` — `setup-agents.sh`, `loc_gate.ps1`, `vault_sync*` | The anti-debt agent *link* (created by `setup-agents.sh`) |
| `stack/agents/anti-debt/` — the debt agent + adapters | The hook *registrations* (per-agent, formats differ) |
| `tools/ai_docs/`, `skills/`, `templates/`, `install.sh` | `tools/ai_docs/config.sh` (git-ignored, per-machine) |

---

## New-machine bootstrap (the whole sequence)

```bash
# 1. Clone
git clone https://github.com/Rwanbt/ai-native-dev-stack.git
cd ai-native-dev-stack

# 2. Link the portable agents (anti-debt) into every detected agent root.
#    Idempotent, OS-aware (symlink on Linux/macOS, junction on Windows).
bash scripts/setup-agents.sh

# 3. Wire the engineering method into each agent config (Layer 1 include) — see per-agent below.

# 4. (Per project) install the AI-docs maintenance stack into a target repo:
cd /path/to/your/project
bash /path/to/ai-native-dev-stack/install.sh
```

Then set the machine-local values:
- `OBSIDIAN_API_KEY` / `OBSIDIAN_API_URL` env vars (used by the memory hooks).
- `tools/ai_docs/config.sh` in each project (Obsidian vault path, graphify, Claude memory key).

---

## Per-agent setup

### Claude Code

1. **Method (Layer 1)** — add near the top of `~/.claude/CLAUDE.md` (global) or a project `CLAUDE.md`:
   ```
   @/absolute/path/to/ai-native-dev-stack/AGENTS.md
   ```
   Keep only Layer 3 (personal/machine) and a Layer-2 appendix (gstack/graphify) in `CLAUDE.md` itself.
2. **Anti-debt agent** — `scripts/setup-agents.sh` links it to `~/.claude/skills/anti-debt`. Activate by loading `@~/.claude/skills/anti-debt/AGENT.md` and running its tools (see [adapter](stack/agents/anti-debt/adapters/claude-code/README.md)). Note: `/skill anti-debt:...` does **not** work (Claude discovers skills flat).
3. **Hooks** — register in `~/.claude/settings.json` (or project `.claude/settings.json`), absolute paths:
   ```json
   {
     "hooks": {
       "SessionStart": [{ "matcher": "", "hooks": [{ "type": "command",
         "command": "node /abs/path/ai-native-dev-stack/hooks/session-start-memory/run.js" }]}],
       "PostToolUse": [{ "matcher": "Edit|Write", "hooks": [{ "type": "command",
         "command": "bash /abs/path/ai-native-dev-stack/hooks/posttool-ai-summary/run_hook.sh" }]}]
     }
   }
   ```
   See [hooks/README.md](hooks/README.md) for the full list and per-hook notes.

### MiniMax (Mavis)

1. **Method (Layer 1)** — Mavis reads its agent's `agent.md`. Reference `AGENTS.md` from it (or include its content) and keep only Mavis-specific Layer 3 there. Do **not** maintain a hand-ported copy of the rules — point at `AGENTS.md`.
2. **Anti-debt agent** — `setup-agents.sh` links it to `~/.mavis/agents/anti-debt`. Run its tools directly (see [adapter](stack/agents/anti-debt/adapters/minimax-code/README.md)):
   ```bash
   python3 ~/.mavis/agents/anti-debt/skills/debt-scan/tools/scan_code.py <repo>
   ```
3. **Hooks** — Mavis supports SessionStart/SessionEnd natively. Create them from the `.md` definitions:
   ```bash
   mavis hook create session-start-memory --event SessionStart --type script --agent mavis
   mavis hook create session-end-save    --event SessionEnd   --type script --agent mavis
   # PreToolUse LOC gate: ~/.mavis/agents/mavis/hooks/pretool-loc-gate.md
   ```
   See per-hook notes in [hooks/](hooks/).

### Cursor

- **Method** — Cursor reads `AGENTS.md` natively at the repo root (and in nested dirs). Cloning the repo into a project, or placing `AGENTS.md` at the project root, is enough. No include needed.
- **Hooks / anti-debt** — run the anti-debt tools manually; Cursor has no SessionStart hook equivalent (use `.cursorrules` for any always-on note).

### Codex

- **Method** — Codex auto-loads `AGENTS.md` at the project root. Same as Cursor.
- **Hooks** — `~/.codex/hooks.json`, same format as Claude Code.

---

## Verifying a transfer

```bash
# Method present and complete:
grep -c "Senior engineering reflexes" AGENTS.md          # → 1

# Agents linked:
bash scripts/setup-agents.sh --dry-run                   # → "already linked correctly" per agent

# Anti-debt runs through an agent path (Claude example):
python3 ~/.claude/skills/anti-debt/skills/debt-scan/tools/scan_code.py .

# AI-docs stack in a project:
# In Claude Code: /verify-ai-docs  → OPERATIONAL
```

A correct transfer means: each agent loads `AGENTS.md` (Layer 1), the anti-debt
agent is linked and runnable, the memory hooks are registered, and the only
hand-edited per-machine file is the agent's own Layer-3 config + `config.sh`.
