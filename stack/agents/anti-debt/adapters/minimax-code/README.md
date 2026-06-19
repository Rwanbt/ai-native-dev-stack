# Adaptateur MiniMax Code

## Installation

Lier le dossier **complet** `anti-debt` (les scanners référencent `tools/` et
`kg/` en relatif — lier `skills/` seul casserait la résolution) :

```bash
mkdir -p ~/.mavis/agents
# macOS / Linux
ln -s /path/to/ai-native-dev-stack/stack/agents/anti-debt ~/.mavis/agents/anti-debt
# Windows (jonction) :
#   New-Item -ItemType Junction -Path "$env:USERPROFILE\.mavis\agents\anti-debt" `
#            -Target "D:\path\to\ai-native-dev-stack\stack\agents\anti-debt"
```

## Activation

Référencer `~/.mavis/agents/anti-debt/AGENT.md` dans le prompt système de
l'agent `mavis`, puis exécuter les outils déterministes :

```bash
python3 ~/.mavis/agents/anti-debt/skills/debt-scan/tools/scan_code.py <repo>
```

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
