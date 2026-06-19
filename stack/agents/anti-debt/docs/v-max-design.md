# V-max Design — Agent Anti-Dette Technique (vue d'ensemble)

> **Statut** : Document de conception, suite à la re-analyse du 2026-06-17
> **Auteur** : Mavis (root session `mvs_52f03dba820246a38a6e9b721f74743f`)
> **Reviewers sollicités** : ChatGPT (reçu), Mistral / Gemini / Claude (à solliciter)
> **Version** : 1.0 (Draft)

## Vue d'ensemble

L'agent vise une utilisation long terme (5+ ans sur un même projet) sans intervention humaine de routine. Il est :

- **Autonome** : exécute des décisions de routine, escalade seulement les cas ambigus
- **Évolutif** : chaque nouvelle information (feedback humain, finding résolu) améliore ses décisions futures
- **Memoryful** : la mémoire du projet n'est jamais perdue, jamais recyclée
- **Critic-driven** : chaque décision est challengée par un moteur d'opposition
- **Préventif** : la dette corrigée ne réapparaît pas (linters auto, CI guards)
- **LLM-agnostique** : fonctionne avec n'importe quel agent IA (Mavis, Claude Code, Codex, Aider, etc.)

## Architecture 7 couches + 1 Layer 0

```
┌─────────────────────────────────────────────────────────┐
│ Layer 7 — Auto-Improvement (V3)                         │
│   • feedback_loop.py      recalibre scoring + taxonomy  │
│   • promote_pattern.py    pattern → skill auto         │
│   • decay_stale.py        confiance findings obsolètes  │
│   • meta_critic.py        audite le Critic lui-même    │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 6 — Prevention Generation (V2.5)                   │
│   • prevent_finding.py    finding → linter rule / test  │
│   • generate_conventions  3+ findings → ADR convention  │
│   • ci_guard.py           pré-receive hook bloquant     │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 5 — Knowledge Graph (V2)                           │
│   • kg_schema.json        nœuds typés                   │
│   • kg_query.py           navigation causale            │
│   • kg_sync.py            sync KG ↔ vault ↔ history    │
│   • kg_decay.py           decay findings non confirmées│
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 4 — Governance Skills (V1.3)                       │
│   • debt-register         CRUD sur Debt Registry         │
│   • architecture-decision ADRs versionnés               │
│   • debt-roadmap          tri valeur × effort × risque  │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 3 — Skills Opérationnels (V1.2)                   │
│   • debt-scan / debt-plan / debt-fix / debt-verify     │
│   • mvp-debt-report / critic                             │
│   • debt-architecture (couplage, cycles, boundaries)     │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 2 — Scanners déterministes (V1 actuel)            │
│   • scan_code.py / scan_security.py / scan_deps.py     │
│   • scan_architecture.py (import-linter, pydeps, madge) │
│   • aggregate.py          fusion normalisée             │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 1 — Core (V1 actuel)                                │
│   • AGENT.md              system prompt LLM-agnostique  │
│   • taxonomy              extensible, pas fermée         │
│   • schemas/*             JSON Schemas versionnés       │
└─────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────┐
│ Layer 0 — Storage (V2, ADR-0023)                          │
│   • KG SQLite (source de vérité)                         │
│   • Findings JSON (cache lecture)                        │
│   • Feedback append-only (events)                        │
│   • Configs YAML (versionné Git)                         │
│   • Vault Obsidian (interface RAG + dashboards)          │
└─────────────────────────────────────────────────────────┘
```

## ADRs de référence

| ADR | Sujet | Statut |
|-----|-------|--------|
| [0023](adr/0023-storage-architecture-v2.md) | Architecture de stockage V2 (SQLite + Vault) | ✅ Proposé |
| [0017](adr/0017-architecture-vmax-7-couches.md) | Architecture V-max 7 couches | ✅ Proposé |
| [0018](adr/0018-threat-model-sandboxing.md) | Threat model + sandboxing des patches | ✅ Proposé |
| [0019](adr/0019-migration-v1-v2.md) | Migration V1 → V2 | ✅ Proposé |
| [0020](adr/0020-concurrence-locking.md) | Concurrence + locking model | ✅ Proposé |
| [0021](adr/0021-critic-self-challenge.md) | Critic self-challenge + métriques anti-biais | ✅ Proposé |
| [0022](adr/0022-versioning-schemas.md) | Backward compatibility + versioning | ✅ Proposé |

## Catalogue des 32 problèmes identifiés

| # | Problème | Couche qui résout | ADR |
|---|----------|-------------------|-----|
| 1 | Migration V1 → V2 | ADR | 0019 |
| 2 | Stratégie de tests V2+ | Toutes | — |
| 3 | SLOs chiffrés V2+ | Toutes | — |
| 4 | Onboarding legacy | Layer 5 | 0023 |
| 5 | Garde-fou Critic | Layer 7 | 0021 |
| 6 | Audit scoring | Layer 7 | 0021 |
| 7 | Backup KG | Layer 0 | 0023 |
| 8 | Interop écosystème | Layer 2 | — |
| 9 | Modèle déploiement | Layer 4 | — |
| 10 | Mode dégradé | Layer 0 | 0023 |
| 11 | Threat model | ADR | 0018 |
| 12 | Kill switch | Layer 7 | 0021 |
| 13 | Concurrence des agents | ADR | 0020 |
| 14 | Mise à jour de l'agent | Layer 0 | 0023 |
| 15 | Licence de la dette | Layer 4 | — |
| 16 | Dette oubliée (expiration) | Layer 4 | — |
| 17 | KG en JSON plat ne scale pas | ADR | 0023 |
| 18 | Versionning des données | ADR | 0022 |
| 19 | Concurrence multi-agents | ADR | 0020 |
| 20 | Cache incrémental | Layer 5 | — |
| 21 | Mode air-gapped | Layer 0 | 0023 |
| 22 | Onboarding utilisateur | Layer 0 + Layer 1 | 0023 |
| 23 | Adoption incrémentale | — | — |
| 24 | Coût estimé | — | — |
| 25 | Métriques satisfaction | Layer 7 | — |
| 26 | RGPD / privacy | ADR | 0018 |
| 27 | Secrets découverts | ADR | 0018 |
| 28 | Divulgation responsable | ADR | 0018 |
| 29 | Negative testing (l'agent ne sait pas ce qu'il ne sait pas) | Layer 5 | — |
| 30 | Méta-Critic | Layer 7 | 0021 |
| 31 | L'agent consomme la dette qu'il combat | Layer 7 + métriques | 0021 |
| 32 | Aucun signal d'arrêt | Layer 7 | 0021 |

**Couverture** : 22/32 problèmes sont adressés par les 7 ADRs. Les 10 restants (#2, #3, #8, #9, #15, #16, #20, #23, #24, #25, #29) sont des **design tasks** à intégrer dans chaque couche au moment de l'implémentation.

## Roadmap révisée (12 mois)

| Mois | Livrable | Couches |
|------|----------|---------|
| 1 (✅) | V1 : core + scans + skills + tests + CI | 1, 2, 3 (subset) |
| 2 | V1.2 : debt-architecture + debt-prevention + debt-manage | 3 (étendu) |
| 3 | V1.3 : debt-registry + ADRs + roadmap | 4 |
| 4-5 | V2 : KG SQLite + queries causales + sync vault | 0, 5 |
| 6-7 | V2.5 : prevention generation + linters auto + CI guards | 6 |
| 8-10 | V3 : auto-improvement loops + critic self-challenge | 7 |
| 11-12 | V3.5 : cross-project learning + ecosystem | — |

## Critères de succès par couche

### Layer 1 (Core) — V1 ✅

- [x] AGENT.md LLM-agnostique
- [x] Taxonomie extensible (5 catégories actives : code, security, dependencies, tests, architecture ; extensions V2 commentées)
- [x] 3 schémas JSON Schema validés
- [x] 8/8 tests unitaires verts

### Layer 2 (Scanners) — V1 ✅

- [x] scan_code.py (Python/Rust/TS/Go/Java)
- [x] scan_security.py (trufflehog/gitleaks/osv-scanner)
- [x] scan_deps.py (cargo/pip/npm audit + depcruise)
- [x] aggregate.py (fusion + tri)
- [x] run_all.sh (orchestrateur)

### Layer 3 (Skills) — V1.2

- [ ] debt-architecture skill (couplage + cycles + boundaries)
- [ ] debt-prevention skill (linters auto)
- [ ] debt-manage skill (CRUD registry)
- [ ] 4 nouveaux tests unitaires
- [ ] Test d'intégration sur Seno (project pilote)

### Layer 4 (Governance) — V1.3

- [ ] debt-registry.json v2 (schéma CRUD)
- [ ] Architecture Decision Records versionnés
- [ ] debt-roadmap.yaml (tri par valeur × effort × risque)
- [ ] Intégration avec Layer 3 (debt-architecture → ADR)
- [ ] Tests d'onboarding (3 cas d'usage : nouveau projet / legacy / greenfield)

### Layer 0 + 5 (Storage + KG) — V2

- [ ] kg_schema.json + SQLite
- [ ] kg_migrate.py (depuis V1)
- [ ] kg_query.py (queries causales : "dettes affectant composant X", "ADRs invalidées par ce fix")
- [ ] kg_sync.py (KG ↔ vault)
- [ ] kg_decay.py (decay findings non confirmées)
- [ ] Test : KG 100k nœuds, query < 100ms p99
- [ ] Test : snapshot vault < 1s, restore KG < 5s

### Layer 6 (Prevention) — V2.5

- [ ] prevent_finding.py (finding → linter rule)
- [ ] generate_conventions.py (3+ findings → ADR convention)
- [ ] ci_guard.py (pre-receive hook)
- [ ] Test : fixer une dette, linter auto-bloque la régression
- [ ] Test : convention générée depuis 5+ findings similaires

### Layer 7 (Auto-Improvement) — V3

- [ ] feedback_loop.py (recalibrage scoring)
- [ ] promote_pattern.py (pattern → skill)
- [ ] decay_stale.py (decay findings obsolètes)
- [ ] meta_critic.py (audit Critic)
- [ ] critic kill switch
- [ ] Test : 100 findings, override 50%, recalibrage → seuils ajustés
- [ ] Test : 0 findings pendant 6 mois → alerte générée
- [ ] Test : override_rate > 30% sur un pattern → alerte

## Tests d'acceptance par milestone

### V1.2 (fin mois 2)

- debt-architecture détecte au moins 3 patterns sur Seno (couplage fort, cycles, etc.)
- debt-prevention génère au moins 1 linter auto qui bloque une régression
- Tests unitaires : 12/12 verts (8 actuels + 4 nouveaux)

### V1.3 (fin mois 3)

- 3 projets onboardés (Seno, VECTORA, HireLens)
- Au moins 5 ADRs créés par l'agent
- Le Debt Registry persiste les décisions prises

### V2 (fin mois 5)

- KG SQLite opérationnel avec > 1000 nœuds
- Queries causales répondent en < 100ms p99
- Vault Obsidian synchronisé quotidiennement
- Migration V1 → V2 sans perte d'historique

### V2.5 (fin mois 7)

- Au moins 10 linters auto-générés depuis findings réels
- Zéro régression des patterns corrigés (vérifié par les CI guards)

### V3 (fin mois 10)

- Critic auto-calibré sur 1000+ feedbacks
- Au moins 1 skill auto-promu depuis un pattern émergent
- 0% de "mort silencieuse" du Critic (signal d'arrêt fonctionne)

## Non-objectifs

- **Remplacer SonarQube** : coexistence, complémentarité
- **Dashboard web** : V-max reste CLI-first, l'output est Markdown/JSON
- **SaaS** : 100% local, 100% open source, MIT
- **Couvrir 100% des patterns de dette** : on vise les 80/20, le Critic challenge les claims de complétude

## Prochaines étapes

1. **Reviewer ce design doc** : 2-3 autres IA (Mistral, Gemini, Claude) avant tout code
2. **Implémenter Layer 0 (storage)** : c'est le fondement, prerequisite pour tout le reste
3. **Migrer V1 → V2** : dual-write + validation croisée + bascule
4. **Implémenter Layer 3 (V1.2)** : debt-architecture, debt-prevention, debt-manage
5. **Continuer vers V1.3, V2, V2.5, V3** : par milestone

## Liens

- [RECAP.md](../RECAP.md) — récap de l'implémentation V1
- [PLAN_IMPLEMENTATION.md](../../../) — plan d'origine (V1, 2026-06-13)
- [routing-guide.md](../../../../routing-guide.md) — routing guide (V1)

---

*Document rédigé le 2026-06-17 par Mavis (session `mvs_52f03dba820246a38a6e9b721f74743f`)*
*Suite à la re-analyse du plan V-max (32 problèmes identifiés)*
