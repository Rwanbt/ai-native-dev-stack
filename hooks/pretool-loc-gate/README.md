# PreToolUse LOC Gate — Hook Universel

## Objectif

Bloquer ou alerter quand un fichier dépasse les seuils de taille déclarés dans
`AGENTS.md` (section *Code structure*).

## Seuils

Les seuils ne sont **pas** écrits dans le script. Ils viennent de
[`conventions.json`](../../conventions.json) à la racine du stack, dont la CI
vérifie qu'il reste aligné sur `AGENTS.md` (`scripts/validate_conventions.py`).

| Condition | Action |
|-----------|--------|
| > 500 LOC (nouveau fichier) | Warning — proposer décomposition |
| > 800 LOC (fichier existant) | Warning — proposer extraction |
| > 1500 LOC (tout fichier) | **BLOCK** — refactoring obligatoire |

Les warnings émettent un champ `reason` au même titre que le blocage : l'agent
reçoit toujours la raison, pas seulement un `metadata` muet.

## Une seule implémentation

`run_gate.js` — Node.js stdlib uniquement, aucun appel à un interpréteur
spécifique à une plateforme. Fonctionne à l'identique sur Linux, macOS et
Windows. `scripts/loc_gate.ps1` a été fusionné dedans et supprimé.

## Trois modes

```bash
node run_gate.js <fichier>   # un fichier — contrat hook PreToolUse
node run_gate.js --staged    # fichiers git staged — pre-commit
node run_gate.js --all       # scan complet du dépôt courant
```

En mode `--staged` et `--all`, seules les extensions listées dans
`conventions.json > scan_extensions` sont examinées, en excluant
`conventions.json > exclude_dirs`.

## Comportement par agent

| Agent | Blocage | Warning |
|---|---|---|
| Mavis (PreToolUse) | `{"_abort":{"reason":"..."}}` | `{"reason":"..."}` |
| Claude Code / Codex / Cursor / OpenCode | exit 1 + `reason` | exit 0 + `reason` |

## Installation

### Claude Code / Codex / OpenCode

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "node /CHEMIN/ABSOLU/hooks/pretool-loc-gate/run_gate.js"
          }
        ]
      }
    ]
  }
}
```

### Pre-commit (tout OS)

```bash
# .git/hooks/pre-commit
node /CHEMIN/ABSOLU/hooks/pretool-loc-gate/run_gate.js --staged || exit 1
```

### Mavis

Déclarer le hook dans `~/.mavis/agents/mavis/hooks/pretool-loc-gate.md` en
pointant sur la même commande `node`.
