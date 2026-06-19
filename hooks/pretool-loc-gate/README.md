# PreToolUse LOC Gate — Hook Universel

## Objectif

Bloquer ou alerter quand un fichier dépasse les seuils LOC définis dans le CLAUDE.md global.

## Seuils LOC (depuis CLAUDE.md global)

| Condition | Action |
|-----------|--------|
| > 500 LOC (nouveau fichier) | Warning — proposer décomposition |
| > 800 LOC (fichier existant) | Warning — proposer extraction |
| > 1500 LOC (tout fichier) | **BLOCK** — refactoring obligatoire |

## Comportement par agent

### Mavis (PreToolUse)

Retourne `{"_abort":{"reason":"..."}}` pour bloquer l'outil si > 1500 LOC.

### Claude Code / Codex / Cursor

Affiche un warning dans la sortie du hook.
Exit code 1 si > 1500 LOC (bloque le hook mais pas l'outil dans certains cas).

## Installation

### Mavis (PreToolUse gate)

```powershell
# Créer via CLI ou fichier:
# C:\Users\barat\.mavis\agents\mavis\hooks\pretool-loc-gate.md
```

### Claude Code / Codex

Ajouter dans `hooks.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "node <chemin>/pretool-loc-gate/run.js"
          }
        ]
      }
    ]
  }
}
```

## Scripts

- `run_gate.sh` — bash (Linux/macOS/Git Bash)
- `run_gate.ps1` — PowerShell (Windows)
- `run_gate.js` — Node.js (universel)
