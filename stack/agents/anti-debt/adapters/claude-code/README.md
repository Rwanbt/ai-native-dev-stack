# Adaptateur Claude Code

## Installation

Dans ton projet, crée le dossier `.claude/skills/` et symlink :

```bash
# Depuis la racine de ton projet
mkdir -p .claude/skills
# Sur Windows (cmd ou PowerShell) :
mklink /D .claude\skills\anti-debt ..\path\to\ai-native-dev-stack\stack\agents\anti-debt\skills

# Ou copie si symlink indisponible
cp -r ../path/to/ai-native-dev-stack/stack/agents/anti-debt/skills/* .claude/skills/anti-debt/
```

## Activation

Dans Claude Code :

```
/skill anti-debt:debt-scan
```

ou en début de session, mentionner l'AGENT.md :

```
@.claude/skills/anti-debt/AGENT.md
```

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
