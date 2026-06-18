# ADR-0017 — Architecture V-max 7 couches (mise à jour)

**Date** : 2026-06-17
**Statut** : Proposé (révision majeure de l'ADR initial "Layered Architecture")
**Décideurs** : Erwan Barat, Mavis
**Remplace** : section "Architecture 4 couches" du plan V1.2 (2026-06-13)
**Re-challengé par** : ChatGPT review 2026-06-17 (32 trous identifiés)

## Contexte

L'architecture initiale V1.2 proposait 4 couches (Core, Skills, Agent Orchestration, Vendor Adapters). Après re-analyse critique :
1. Le scope "Agent Orchestration" était sous-spécifié (LLM-agnostique vs LLM-spécifique)
2. Aucune couche de **stockage** dédiée → state management = JSON plats
3. Aucune couche de **gouvernance** (registry, ADRs) → décisions ad-hoc
4. Aucune couche de **prévention** → l'agent ne fait que détecter/corriger, jamais empêcher
5. Aucune couche d'**auto-amélioration** → l'agent ne s'améliore pas de lui-même

L'agent vise une utilisation long terme (5+ ans sur un même projet) sans intervention humaine de routine. Il doit donc être **autonome**, **évolutif**, et **memoryful**.

## Décision

**Architecture V-max = 7 couches + 1 couche stockage (Layer 0)** :

```
┌─────────────────────────────────────────────────────────┐
│ Layer 7 — Auto-Improvement (V3, ~10 mois)               │
│   feedback_loop.py      recalibre scoring + taxonomy      │
│   promote_pattern.py    pattern → skill auto             │
│   decay_stale.py        confiance findings obsolètes      │
│   meta_critic.py        audite le critic lui-même        │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 6 — Prevention Generation (V2.5, ~6-7 mois)         │
│   prevent_finding.py    finding → linter rule / test      │
│   generate_conventions  3+ findings → ADR convention     │
│   ci_guard.py           pré-receive hook bloquant         │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 5 — Knowledge Graph (V2, ~4-5 mois)                 │
│   kg_schema.json        nœuds typés                       │
│   kg_query.py           navigation causale                │
│   kg_sync.py            sync KG ↔ vault ↔ debt-history    │
│   kg_decay.py           decay des findings non confirmées│
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 4 — Governance Skills (V1.3, ~3 mois)               │
│   debt-register         CRUD sur le Debt Registry         │
│   architecture-decision ADRs versionnés                   │
│   debt-roadmap          tri par valeur × effort × risque │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 3 — Skills Opérationnels (V1.2 actuel, ~2 mois)     │
│   debt-scan / debt-plan / debt-fix / debt-verify        │
│   mvp-debt-report / critic                               │
│   debt-architecture (couplage, cycles, boundaries)       │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 2 — Scanners déterministes (V1 actuel)              │
│   scan_code.py / scan_security.py / scan_deps.py        │
│   scan_architecture.py (import-linter, pydeps, madge)   │
│   aggregate.py          fusion normalisée                 │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│ Layer 1 — Core (V1 actuel)                                 │
│   AGENT.md              system prompt LLM-agnostique      │
│   taxonomy              extensible, pas fermée             │
│   schemas/*             JSON Schemas strictes + version   │
└─────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────┐
│ Layer 0 — Storage (V2, ADR-0023)                           │
│   KG SQLite (source de vérité)                            │
│   Findings JSON (cache lecture)                          │
│   Feedback append-only (events)                           │
│   Configs YAML (versionné Git)                            │
│   Vault Obsidian (interface RAG + dashboards)             │
└─────────────────────────────────────────────────────────┘
```

## Conséquences

### Positives

- **Séparation claire** : chaque couche a une responsabilité unique
- **Évolutivité** : on peut arrêter après n'importe quelle couche et avoir un système fonctionnel
- **Testabilité** : chaque couche est testable indépendamment
- **Interopérabilité** : Layer 0 (storage) et Layer 2 (scanners) sont LLM-agnostiques
- **Auto-amélioration possible** : Layer 7 + Layer 5 permettent la méta-cognition

### Négatives / Trade-offs

- **Complexité initiale** : 8 couches semblent lourdes pour un "simple" agent anti-dette
  - Mitigation : chaque couche est livrable séparément, on ship V1.2 d'abord
- **Risque d'over-engineering** : Layer 6-7 sont speculative
  - Mitigation : ADRs séparés, chaque layer doit prouver sa valeur avant que la suivante ne soit construite
- **Vault Obsidian = dépendance externe** : si Obsidian tombe, l'interface est down
  - Mitigation : Layer 0 (SQLite) reste opérationnel, vault = bonus

## Alternatives rejetées

- **Architecture plate (1 fichier)** : non testable, non extensible
- **Architecture microservices** : sur-ingénierie, couplage réseau inutile
- **Mono-couche avec tout dedans** : comme l'agent V0, mélange config/scanner/gouvernance/UI
- **Layered classique (3 couches)** : insuffisant pour supporter gouvernance + auto-amélioration

## Critères d'acceptation

Chaque couche doit avoir, avant d'être considérée livrée :
- **Spec documentée** dans `docs/adr/NNNN-{couche}.md`
- **Schéma de données** (JSON Schema ou SQL) versionné
- **Tests unitaires** (couverture > 80% sur le code critique)
- **Test d'intégration** end-to-end documenté
- **Métriques de succès** chiffrées
- **Threat model** documenté
- **Migration depuis la couche précédente** documentée

## Liens

- ADR-0023 (storage V2)
- ADR-0018 (threat model)
- ADR-0019 (migration V1 → V2)
- ADR-0020 (concurrence)
- ADR-0021 (critic self-challenge)
- ADR-0022 (versionning des schémas)
