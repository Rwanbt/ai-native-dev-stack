# Anti-Dette Technique — Agent de gouvernance

> **Statut** : V1 + V1.2 + Layer 0 (Knowledge Graph) livrés. Roadmap V2-V3 : voir [`docs/v-max-design.md`](docs/v-max-design.md).
> **Statut détaillé & tests** : [`RECAP.md`](RECAP.md) et [`CHANGELOG.md`](CHANGELOG.md) font foi (source unique — ne pas re-déclarer le compte de tests ailleurs).
> **Installation** : voir [`INSTALL.md`](INSTALL.md).
> **Compatible** : MiniMax Code, Claude Code, Gemini CLI, Codex, Aider, Continue.dev

## Vue d'ensemble

Cet agent détecte, classe, priorise et corrige la dette technique de manière :
- **Portable** : fonctionne dans n'importe quel CLI agent IA
- **Outillage déterministe d'abord** : ruff, clippy, osv-scanner, trufflehog font la détection primaire
- **Critic Engine obligatoire** : aucun finding/plan/fix sans validation
- **Historique persistant** : `.debt-history.json` suit l'évolution
- **Anti-MVP** : MVP explicite = dette tracée, pas cachée

## Architecture

```
anti-debt/
├── AGENT.md                  # System prompt LLM-agnostique
├── taxonomy/
│   └── debt-categories.yaml  # 4 catégories V1 (code, security, dependencies, tests)
├── schemas/
│   ├── debt-finding.schema.json
│   ├── debt-triage.schema.json   # sortie déterministe du Critic (tiers)
│   ├── debt-plan.schema.json     # plan de remédiation jugé (skill LLM)
│   └── debt-history.schema.json
├── skills/                   # 6 skills portables (commit 2)
├── adapters/                 # Adaptateurs CLI agents (commit 6)
├── examples/                 # Fichiers d'exemple (commit 1)
├── tests/                    # Tests de validation (commits 4-5)
└── INSTALL.md                # Procédure d'installation
```

## Cycle de gouvernance

```
Discovery → Analysis → Prioritization → Planning → Remediation → Verification → Prevention
```

## Catégories V1

| Catégorie | Sous-catégories | Outils primaires |
|-----------|------------------|------------------|
| **code** | duplication, complexity, dead_code, god_classes, error_handling, type_safety | ruff, clippy, eslint, golangci-lint |
| **security** | known_vulns, secrets_in_code, unsafe_io, weak_crypto, auth_issues | trufflehog, gitleaks, osv-scanner |
| **dependencies** | outdated, abandoned, malicious, circular, heavy_unused | dependency-cruiser, cargo audit, npm audit, pip-audit |
| **tests** | coverage_gaps, flaky_tests, missing_integration, outdated_mocks | coverage.py, cargo tarpaulin, jest |

Extensions V2+ : architecture, observability, ai_agent.

## Utilisation

Voir `INSTALL.md` pour l'installation, puis :

```bash
# Audit complet
debt-scan /path/to/repo

# Avec agent CLI
# MiniMax Code:
/skill anti-debt:debt-scan
# Claude Code:
/skill anti-debt:debt-scan
```

## Pourquoi cet agent existe

Les LLM ont trois biais systémiques sur la dette technique :
1. **Biais MVP** : plans complets → MVP non labellisé → dette involontaire
2. **Biais local** : solutions localement optimales, pas globalement cohérentes
3. **Biais de complétude annoncée** : "voilà c'est livré" + 80% du contenu manquant

Cet agent est conçu pour les détecter et les corriger.

## Licence

MIT — voir `LICENSE` à la racine de `ai-native-dev-stack/`.
