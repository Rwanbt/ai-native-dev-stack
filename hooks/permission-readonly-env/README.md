# PermissionRequest Read-Only Env Prefix — Hook Universel

## Objectif

Auto-allow les commandes Bash read-only qui ont des préfixes de variables d'environnement.
Exemples : `RUST_LOG=debug cat file.txt`, `LANG=fr ls -la`, `DEBUG=1 grep pattern file`.

Le hook strip le préfixe ENV_VAR=value, identifie la commande réelle, et si elle est
read-only (cat, ls, grep, etc.), émet `permissionDecision: allow`.

## Ce que fait ce hook

1. Lit `tool_input.command` du payload JSON
2. Skip les tokens `KEY=VALUE` au début
3. Identifie le premier mot non-env-var
4. Si dans la whitelist read-only → autorise

## Sortie (format universel)

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "permissionDecision": "allow",
    "permissionDecisionReason": "read-only command 'cat' with env var prefix"
  }
}
```

## Whitelist

```python
READONLY = {
    'ls', 'll', 'cat', 'head', 'tail', 'grep', 'rg',
    'wc', 'diff', 'echo', 'pwd', 'which', 'file',
    'stat', 'type', 'dir', 'find', 'awk', 'cd',
}
```

## Script

Voir `run.py` (Python stdlib uniquement).

## Installation par agent

### Codex

Dans `.codex/hooks.json` :
```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 <chemin>/hooks/permission-readonly-env/run.py"
          }
        ]
      }
    ]
  }
}
```

## Source originale

Portée depuis la configuration Codex personnelle de l'auteur.
