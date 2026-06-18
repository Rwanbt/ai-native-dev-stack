# Installation de l'agent anti-dette

## Pré-requis

### Outils (au moins 1 par catégorie)

| Catégorie | Outils recommandés |
|-----------|---------------------|
| Code | `ruff` (Python), `cargo clippy` (Rust), `eslint` (TS/JS), `golangci-lint` (Go) |
| Sécurité | `trufflehog` ou `gitleaks` + `osv-scanner` |
| Dépendances | `dependency-cruiser` + (`cargo audit` OU `npm audit` OU `pip-audit`) |
| Tests | `coverage.py`, `cargo tarpaulin`, `jest --coverage` |

### Python
- Python 3.11+ (le core tourne en stdlib, pas de dépendances tierces)

## Installation par CLI agent

### MiniMax Code
```bash
mkdir -p .minimax/skills/
ln -s ../../stack/agents/anti-debt/skills .minimax/skills/anti-debt
```
Puis : `/skill anti-debt:debt-scan`

### Claude Code
```bash
mkdir -p .claude/skills/
ln -s ../../stack/agents/anti-debt/skills .claude/skills/anti-debt
```
Puis : `/skill anti-debt:debt-scan`

### Gemini CLI
```bash
mkdir -p .gemini/skills/
ln -s ../../stack/agents/anti-debt/skills .gemini/skills/anti-debt
```
Puis : `/skill anti-debt:debt-scan`

### Codex / Aider / Continue.dev / autres
Voir `adapters/generic/README.md` — chargement manuel des skills via prompt système.

## Vérification de l'installation

```bash
# Vérifier que la taxonomie est chargée
python3 -c "import yaml; d=yaml.safe_load(open('taxonomy/debt-categories.yaml')); print(f'{len([k for k in d if not k.startswith(\"severity\")])} categories loaded')"

# Vérifier les schémas
python3 -c "import json; [json.load(open(f'schemas/{f}')) for f in ['debt-finding.schema.json', 'debt-triage.schema.json', 'debt-plan.schema.json', 'debt-history.schema.json']]; print('all schemas valid')"
```

## Premier scan (après Commit 3)

```bash
# Sur votre propre repo
bash skills/debt-scan/tools/run_all.sh /path/to/your/repo
```

## Mise à jour

```bash
cd ai-native-dev-stack/
git pull
# Vos symlinks pointent vers stack/agents/anti-debt/ — ils sont auto-mis-à-jour
```
