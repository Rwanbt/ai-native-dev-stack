# SessionStart Memory Loader — Hook Universel

## Objectif

Charger automatiquement le contexte de session au démarrage de tout agent IA (Mavis, Claude Code, Codex, Cursor, etc.).

## Ce que fait ce hook

1. Lit `memory/user.md` (profil Erwan, projets, workflow)
2. Lit `_global/handoff.md` (état courant de tous les projets)
3. Affiche un résumé de session précédente (si existante)

## API Obsidian Locale

- Base URL: `http://127.0.0.1:27123` (override via `OBSIDIAN_API_URL`)
- Auth: `Authorization: Bearer <API_KEY>`
- API Key: lue depuis la variable d'environnement `OBSIDIAN_API_KEY` (jamais commitée)

## Installation par agent

### Mavis
```powershell
# Ce hook est déjà installé via:
# mavis hook create session-start-memory --event SessionStart --type script --agent mavis
# Fichier: C:\Users\barat\.mavis\agents\mavis\hooks\session-start-memory.md
```

### Claude Code
Ajouter dans `~/.claude/hooks.json` (global) ou `<projet>/.claude/hooks.json` (par projet):
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "node <chemin>/session-start-memory/run.js"
          }
        ]
      }
    ]
  }
}
```

### Codex
Ajouter dans `~/.codex/hooks.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "node <chemin>/session-start-memory/run.js"
      }
    ]
  }
}
```

### Cursor
Via le plugin MCP Tools ou `.cursor/mcp.json` (consulter documentation Cursor).

## Script

Voir `run.js` (Node.js, stdlib uniquement).
