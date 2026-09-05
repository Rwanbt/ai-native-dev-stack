# SessionEnd Memory Saver — Hook Universel

## Objectif

Sauvegarder automatiquement l'état de session à la fin de tout agent IA.

## Ce que fait ce hook

1. Appende une entrée dans `LOG.md` du vault avec date + résumé
2. Met à jour `_memory/memory.md` du projet actif (si identifiable)

## API Obsidian Locale

- Base URL: `http://127.0.0.1:27123`
- Auth: `Authorization: Bearer <API_KEY>`

## Script

Voir `run.js` (Node.js, stdlib uniquement).

## Installation par agent

### Mavis
```powershell
# Ce hook est déjà installé via:
# mavis hook create session-end-save --event SessionEnd --type script --agent mavis
# Fichier: ~/.mavis/agents/mavis/hooks/session-end-save.md
```

### Claude Code / Codex / Cursor
Comme pour session-start-memory, ajouter dans le fichier hooks.json de l'agent.
