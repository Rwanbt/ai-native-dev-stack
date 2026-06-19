# PreToolUse Graphify Inject — Hook Universel

## Objectif

Quand un agent CLI tape une commande `grep`/`rg`/`find`/`ack`/`ag` sur un repo qui contient
`graphify-out/graph.json`, le hook injecte automatiquement le contexte du graphe de dépendances
dans la conversation — pour éviter de re-chercher dans le code alors qu'un graphe existe.

## Ce que fait ce hook

Lit la commande Bash entrante. Si elle contient un outil de recherche (`grep`, `rg`, etc.)
ET que `graphify-out/graph.json` existe dans le cwd, le hook émet un
`additionalContext` pointant vers `graphify-out/GRAPH_REPORT.md`.

## Sortie (format universel)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."
  }
}
```

## Scripts

- `run.js` (Node.js, stdlib uniquement)
- `run.py` (Python, stdlib uniquement)

## Installation par agent

### Claude Code / Codex / MiniMax Code

Dans le `hooks.json` du projet (ou global) :

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "node <chemin>/hooks/pretool-graphify-inject/run.js"
          }
        ]
      }
    ]
  }
}
```

## Source originale

Portée depuis `C:\Users\barat\.codex\hooks.json` (Erwan Barat) qui utilisait un
bash inline avec `case "$CMD"`. La version Node.js est multiplateforme sans dépendance bash.
