# Hooks — Installation multi-agent

> Ce dossier contient les hooks universels de AI Native Dev Stack, installables sur tout agent IA.

## Les 4 hooks universels

| Hook | Event | Trigger | Agents |
|------|-------|---------|--------|
| `session-start-memory/` | SessionStart | démarrage session | Tous |
| `session-end-save/` | SessionEnd | fin de session | Tous |
| `posttool-ai-summary/` | PostToolUse | Edit ou Write | Claude Code, Codex, Cursor |
| `pretool-loc-gate/` | PreToolUse | avant Edit/Write | Mavis (PreToolUse), Claude Code, Codex |

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
# C:\Users\barat\.mavis\agents\mavis\hooks\pretool-loc-gate.md
```

## Installation Claude Code

### Global hooks
`~/.claude/hooks.json`:
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
pwsh -NoProfile -File 'D:/App/ai-native-dev-stack/scripts/vault_sync_once_daily.ps1'
```

## Installation Codex

`~/.codex/hooks.json` — même format que Claude Code.

## Installation Cursor

Cursor utilise `.cursorrules` et les plugins MCP.
Vérifier la documentation Cursor pour l'équivalent de `hooks.json`.

## Notes

- API Obsidian locale: `http://127.0.0.1:27123` (override via `OBSIDIAN_API_URL`)
- API Key: lue depuis la variable d'environnement `OBSIDIAN_API_KEY` (jamais commitée).
  Récupérer la clé dans Obsidian → plugin *Local REST API* → puis l'exporter :
  `setx OBSIDIAN_API_KEY "<votre-clé>"` (Windows) / `export OBSIDIAN_API_KEY=...` (bash)
- Prérequis: Obsidian ouvert avec le vault `IA_Dev_Brain` + plugin Local REST API activé
