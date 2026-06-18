# Adaptateur MiniMax Code

## Installation

Dans ton projet, crée le dossier `.mavis/agents/` et copie les skills :

```bash
mkdir -p .mavis/agents/
ln -s ../../path/to/ai-native-dev-stack/stack/agents/anti-debt .mavis/agents/anti-debt
```

## Activation

Dans MiniMax Code, les skills sont auto-découverts si placés dans
`.mavis/agents/<name>/skills/`. L'AGENT.md de l'agent `mavis` peut référencer
ces skills via prompt système.

## Hooks custom Mavis recommandés

Dans `~/.mavis/agents/mavis/hooks/`, ajouter un hook SessionStart qui
charge la taxonomie :

```yaml
---
hookEvent: SessionStart
type: script
priority: 15
matcher: ""
timeout: 10000
---

```bash
node -e "
const fs = require('fs');
const yaml = fs.readFileSync('<path>/anti-debt/taxonomy/debt-categories.yaml', 'utf8');
console.log(JSON.stringify({ metadata: { antiDebtTaxonomy: 'loaded', categories: yaml.split('\n').filter(l => l.match(/^[a-z]+:$/)).length } }));
"
```
```

## Permissions

Ajouter dans `.mavis/agents/mavis/config.yaml` :

```yaml
permissions:
  allow:
    - "Bash(python3:*)"
    - "Bash(ruff:*)"
    - "Bash(trufflehog:*)"
    - "Bash(osv-scanner:*)"
```
