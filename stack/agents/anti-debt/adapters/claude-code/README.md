# Adaptateur Claude Code

## Installation

Lier le dossier **complet** `anti-debt` (PAS seulement `skills/`) — les scanners
référencent `tools/` et `kg/` en relatif, donc lier `skills/` seul casse la
résolution. `Path.resolve()` suit les liens, donc un lien/jonction du dossier
entier fonctionne.

```bash
# macOS / Linux
ln -s /path/to/ai-native-dev-stack/stack/agents/anti-debt ~/.claude/skills/anti-debt

# Windows (jonction — pas besoin d'admin) :
#   New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\anti-debt" `
#            -Target "D:\path\to\ai-native-dev-stack\stack\agents\anti-debt"
```

## Activation

L'agent est un **agent** (system prompt + outils), pas un skill plat
auto-découvert. Deux usages :

```
# 1. Charger le system prompt en début de session :
@~/.claude/skills/anti-debt/AGENT.md

# 2. Lancer un scan déterministe directement :
python3 ~/.claude/skills/anti-debt/skills/debt-scan/tools/scan_code.py <repo>
python3 ~/.claude/skills/anti-debt/tools/critic_v2.py score findings.json triage.json
```

> Note : `/skill anti-debt:debt-scan` ne fonctionne PAS — Claude Code découvre
> les skills à plat (`~/.claude/skills/<nom>/SKILL.md`), or les skills de l'agent
> sont imbriqués sous `skills/`. Réfère-les via `@` ou exécute les outils.

## Permissions recommandées

Ajouter dans `.claude/settings.json` du projet :

```json
{
  "permissions": {
    "allow": [
      "Bash(python3:*)",
      "Bash(bash:*)",
      "Bash(ruff:*)",
      "Bash(trufflehog:*)",
      "Bash(osv-scanner:*)"
    ]
  }
}
```

## Hook PreToolUse (optionnel)

Pour intégrer le gate LOC de l'agent anti-dette dans les autres outils
de Claude Code, voir `hooks-examples/pretool-loc-gate.json` (V2).
