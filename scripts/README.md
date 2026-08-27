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

## vault_sync.py — Obsidian vault sync

The single implementation; `vault_sync.ps1`, `vault_sync.sh` and
`vault_sync_once_daily.ps1` are shims that locate Python and delegate.

```bash
python scripts/vault_sync.py --vault /path/to/vault
python scripts/vault_sync.py --dry-run          # report, change nothing
python scripts/vault_sync_once_daily.py         # at most one sync per day
```

Vault path resolution: `--vault`, else `$OBSIDIAN_VAULT`, else an error.
Sentinel location: `$OBSIDIAN_SYNC_STATE`, else next to the script.

### What it guarantees

| Guarantee | Why it exists |
|---|---|
| Never reports a success it has not verified | The push is confirmed by re-reading the remote ref afterwards. The previous version printed "pushed to GitHub" after a no-op, and 13 days of notes were never backed up. |
| Pushes the branch that is checked out | The previous version pushed a hardcoded `master`, so a vault sitting on any other branch was silently never pushed. |
| Refuses a non-primary branch | A vault has no reason to carry branches, and a side branch is exactly how the backup stopped working. Override with `--allow-branch`. |
| Refuses to push credentials | Staged content is scanned with the stack's shared `SECRET_PATTERNS` before any commit. |
| Stops on divergence, exits non-zero | Guessing a merge on someone's second brain is not acceptable. |
| Single writer | A lock in `.git/` — never in the working tree, or the vault is permanently dirty and the lock gets committed with the notes. |
| A failed sync does not mark the day done | `vault_sync_once_daily.py` writes its sentinel only on exit 0. The previous version wrote it unconditionally, so a failure suppressed retries until the next day. |

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
