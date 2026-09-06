# Hooks — Installation multi-agent

> Ce dossier contient les hooks universels de AI Native Dev Stack, installables sur tout agent IA.

## Les hooks fournis

| Hook | Event | Trigger | Agents |
|------|-------|---------|--------|
| `session-start-memory/` | SessionStart | démarrage session | Tous |
| `session-end-save/` | SessionEnd | fin de session | Tous |
| `posttool-ai-summary/` | PostToolUse | Edit ou Write | Claude Code, Codex, Cursor |
| `pretool-loc-gate/` | PreToolUse | avant Edit/Write | Mavis (PreToolUse), Claude Code, Codex |
| `pretool-graphify-inject/` | PreToolUse | grep/rg/find via Bash | Claude Code, Codex, MiniMax (manual install — see its README) |

## Installation Mavis

Mavis supporte nativement les hooks SessionStart et SessionEnd via `mavis hook create`.

```powershell
# SessionStart memory loader (déjà installé)
mavis hook list --agent mavis --human

# SessionEnd save (déjà installé)
mavis hook list --agent mavis --human
```

Pour le LOC gate (PreToolUse):
```powershell
# Créer manuellement via le fichier hook:
# ~/.mavis/agents/mavis/hooks/pretool-loc-gate.md
```

## Installation Claude Code

### Global hooks
`~/.claude/settings.json`:
```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "node <chemin>/hooks/session-start-memory/run.js"
      }]
    }],
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "bash <chemin>/hooks/posttool-ai-summary/run_hook.sh"
      }]
    }]
  }
}
```

### Vault sync quotidien
Dans `~/.claude/CLAUDE.md`, section début de session:
```powershell
pwsh -NoProfile -File '<STACK_ROOT>/scripts/vault_sync_once_daily.ps1'
```

## Installation OpenCode (Linux)

`python3 scripts/install_agents.py` installe le plugin natif
`~/.config/opencode/plugins/ai-native-dev-stack.ts`. Il adapte les événements
OpenCode au LOC gate et au générateur `AI_SUMMARY.md`; aucun fichier de
configuration utilisateur n'est écrasé.

## Installation Codex

Utiliser les hooks natifs Codex. Les payloads et décisions ne sont pas
identiques à ceux de Claude Code; ne pas recopier le JSON Claude tel quel.

## Installation Cursor

Cursor supporte ses propres règles et hooks. Utiliser son format natif; les
skills partagés sont installés sous `~/.agents/skills/` sur Linux.

## Notes

- API Obsidian locale: `http://127.0.0.1:27123` (override via `OBSIDIAN_API_URL`)
- API Key: lue depuis la variable d'environnement `OBSIDIAN_API_KEY` (jamais commitée).
  Récupérer la clé dans Obsidian → plugin *Local REST API* → puis l'exporter :
  `setx OBSIDIAN_API_KEY "<votre-clé>"` (Windows) / `export OBSIDIAN_API_KEY=...` (bash)
- Prérequis: Obsidian ouvert avec votre vault `<OBSIDIAN_VAULT>` + plugin Local REST API activé
