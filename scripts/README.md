# Scripts — AI Native Dev Stack

## install_agents.py — global installer

The single implementation of the machine-level install: links every skill and
agent into each detected AI CLI root, and writes a managed instruction block
referencing `AGENTS.md` into each CLI's global config.

Cross-platform. On Windows, directory links fall back to junctions when
symlink creation is denied (junctions need neither admin rights nor Developer
Mode), so no elevated shell is required.

```bash
python scripts/install_agents.py              # install
python scripts/install_agents.py --dry-run    # show what would change
python scripts/install_agents.py --check      # verify an existing install
python scripts/install_agents.py --home PATH  # target another home directory
```

Idempotent: a second run reports `0 change(s)`. It never overwrites a path it
does not own — an unmanaged file is reported as `KEEP`, not replaced.

Agent roots it writes to:

| CLI | Skills | Global instructions |
|---|---|---|
| Claude Code | `~/.claude/skills` | `~/.claude/CLAUDE.md` |
| Codex / OpenCode / Cursor | `~/.agents/skills` | `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md` |
| MiniMax (Mavis) | `~/.mavis/agents` | `~/.mavis/agents/mavis/agent.md` |

## setup-agents.sh / setup-agents.ps1 — entry points

Thin shims that locate a working Python and delegate to `install_agents.py`.
They exist so neither shell is a prerequisite for the other's platform.

```bash
bash scripts/setup-agents.sh --dry-run                    # Linux / macOS / Git Bash
pwsh -NoProfile -File scripts/setup-agents.ps1 -DryRun    # Windows, no Git Bash
```

## validate_conventions.py — anti-drift gate

Fails when `AGENTS.md` and `conventions.json` declare different thresholds.
`AGENTS.md` is the human-readable source; `conventions.json` is what the
tooling reads. Run in CI.

```bash
python scripts/validate_conventions.py
```

Without this gate the two silently diverged: complexity `>25 blocking` shipped
as `20`, and function size `>200 blocking` was never implemented at all.

## sync_inlined_method.py

Keeps the inlined copy of the engineering method in sync with `AGENTS.md` for
tools that cannot follow an `@include`.

## vault_sync_once_daily.ps1 / vault_sync.ps1

Obsidian vault sync, run once per day at first session.

> **Status: placeholder.** `vault_sync.ps1` in this repo does not sync
> anything — it prints a notice and exits 0. A working per-machine version
> exists outside this repo. Do not rely on the committed copy for backups
> until it is replaced by a real, parameterised implementation.
>
> Known defect to fix at the same time: `vault_sync_once_daily.ps1` writes its
> "synced today" sentinel unconditionally, including when the sync reported a
> divergence and pushed nothing — which disables retries for the rest of the
> day.

```powershell
pwsh -NoProfile -File scripts/vault_sync_once_daily.ps1
```

## The LOC gate lives elsewhere

`loc_gate.ps1` was merged into `hooks/pretool-loc-gate/run_gate.js`, now the
only implementation of the rule. Node stdlib, identical on every OS, three
modes:

```bash
node hooks/pretool-loc-gate/run_gate.js <file>     # one file — PreToolUse hook
node hooks/pretool-loc-gate/run_gate.js --staged   # git staged files — pre-commit
node hooks/pretool-loc-gate/run_gate.js --all      # full repo scan
```

Thresholds come from `conventions.json`, not from the script.

**Pre-commit integration** (`.git/hooks/pre-commit`, any OS):
```bash
node /path/to/ai-native-dev-stack/hooks/pretool-loc-gate/run_gate.js --staged || exit 1
```
