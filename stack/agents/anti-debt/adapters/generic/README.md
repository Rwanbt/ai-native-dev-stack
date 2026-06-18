# Adaptateur générique — Installation manuelle

> Pour les CLI agents qui ne supportent pas le chargement automatique de skills
> (Codex CLI, Aider, Continue.dev, Windsurf, etc.)

## Méthode 1 — Prompt système

Charge les skills dans le prompt système au démarrage de la session :

```text
Tu as accès aux skills suivants :

=== SKILL: debt-scan ===
[fichier skills/debt-scan/SKILL.md complet]
=== END SKILL ===

=== SKILL: debt-plan ===
[fichier skills/debt-plan/SKILL.md complet]
=== END SKILL ===

[etc. pour debt-fix, debt-verify, mvp-debt-report, critic]

Tu appliques strictement les directives de AGENT.md (le system prompt).
```

## Méthode 2 — Fichier de config

Si l'agent supporte un fichier `AGENTS.md` ou `CONVENTIONS.md` à la racine du projet :

```bash
# Symlink ou copie
cp AGENT.md /path/to/project/AGENTS.md
# Les skills deviennent des instructions portables
```

## Méthode 3 — CLI direct (sans agent)

Pour utiliser les outils sans agent IA :

```bash
# Scan déterministe pur (LLM optionnel)
bash skills/debt-scan/tools/run_all.sh /path/to/repo

# Validation de plan contre le schéma
python3 -c "
import json, jsonschema
plan = json.load(open('.debt-plan.json'))
schema = json.load(open('schemas/debt-plan.schema.json'))
jsonschema.validate(plan, schema)
print('plan OK')
"
```

## Compatibilité testée

| Agent | Skill loading | Hook PreToolUse | Adaptateur |
|-------|---------------|------------------|------------|
| MiniMax Code | ✅ natif | ✅ | `adapters/minimax-code/` (commit 6) |
| Claude Code | ✅ natif | ✅ | `adapters/claude-code/` (commit 6) |
| Gemini CLI | ✅ natif | ⚠️ partiel | `adapters/gemini-cli/` (V2) |
| Codex CLI | ⚠️ manuel | ❌ | cette page |
| Aider | ⚠️ conventions | ❌ | cette page |
| Continue.dev | ⚠️ prompt | ❌ | cette page |
| Windsurf | ⚠️ rules | ❌ | cette page |

## Vérification rapide

```bash
# Le core est-il chargeable ?
python3 -c "
import yaml, json
print('Taxonomy:', len([k for k in yaml.safe_load(open('taxonomy/debt-categories.yaml')) if not k.startswith('severity')]), 'categories')
print('Schemas:', len(list(__import__('pathlib').Path('schemas').glob('*.json'))), 'JSON schemas')
"
```
