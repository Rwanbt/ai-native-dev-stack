# PostToolUse AI_SUMMARY Generator — Hook Universel

## Objectif

Après un Edit ou Write de fichier source, régénérer le `AI_SUMMARY.md` du module concerné.
C'est le hook central du stack AI Native Dev — il maintient les summaries auto-générés à jour.

## Principe de fonctionnement

Le hook détecte le fichier modifié, trouve le `AI_CONTEXT.md` parent le plus proche,
puis appelle `generate_ai_summary.py` pour régénérer le `AI_SUMMARY.md` du module.

## Dépendances

- Python ≥ 3.8 (stdlib uniquement)
- Scripts AI Native Dev Stack: `tools/ai_docs/update_on_edit.py`, `tools/ai_docs/generate_ai_summary.py`

## Installation par agent

### Claude Code / Codex

Ajouter dans `.claude/hooks.json` (projet) ou `~/.claude/hooks.json` (global):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash <chemin>/posttool-ai-summary/run_hook.sh"
          }
        ]
      }
    ]
  }
}
```

### Mavis

Mavis ne supporte pas nativement PostToolUse sur Edit/Write.
Alternative: utiliser un PreToolUse gate qui enregistre le fichier edité,
puis un cron job périodique qui régénère les summaries.

Alternative viable: installer via MCP Obsidian un hook de notification
quand un fichier change, et régénérer les summaries en réponse.

### Cursor / Continue

Via `.cursorrules` ou plugin MCP Tools compatible.

## Scripts

- `run_hook.sh` — wrapper bash (Linux/macOS/Git Bash Windows)
- `run_hook.ps1` — wrapper PowerShell (Windows natif)

## Configuration

Le hook utilise `GRAPHIFY_BIN` et `OBSIDIAN_API_KEY` si définis.
Voir `tools/ai_docs/config.sh.example` pour la configuration.
