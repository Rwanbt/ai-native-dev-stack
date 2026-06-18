# ADR-0023 — Architecture de stockage V2 : SQLite KG + Vault Obsidian

**Date** : 2026-06-17
**Statut** : Proposé
**Décideurs** : Erwan Barat, Mavis
**Source de vérité** : plan V-max (chat 2026-06-17)

## Contexte

L'agent V1 utilise des fichiers JSON plats pour stocker son état :
- `debt-history.json`
- `debt-plan.json`
- `debt-scan.json`

Ces fichiers posent 4 problèmes identifiés pendant la re-analyse du plan V-max :

1. **Pas scalable** : pour un projet de 300k+ LOC, l'historique complet devient rapidement > 100 MB → chargement complet en mémoire à chaque accès
2. **Pas queryable** : impossible de faire des queries causales (ex: "quelles dettes affectent ce composant ?") sans charger tout
3. **Pas concurrent-safe** : pas de locking, deux sessions parallèles corromptent l'état
4. **Pas intégré au vault** : l'humain doit lire des JSON bruts au lieu d'avoir une vue Obsidian

## Décision

**Architecture de stockage V2 = double-couche** :

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 0 — Storage opérationnel (rapide, queryable)           │
│                                                              │
│   ~/.mavis/kg.db           SQLite, schéma relationnel strict  │
│   ~/.mavis/findings/       JSON par scan (archivage)          │
│   ~/.mavis/feedback/       JSON append-only (events)          │
│   ~/.mavis/configs/        YAML, versionné Git                │
└──────────────────────────────────────────────────────────────┘
                              ↕ sync bidirectionnel
┌──────────────────────────────────────────────────────────────┐
│ Layer 1 — Interface humaine (RAG-friendly, dashboard)         │
│                                                              │
│   Vault Obsidian :                                            │
│     AntiDebt/snapshots/kg-{date}.md     (snapshot KG)        │
│     AntiDebt/decisions/adr-*.md        (ADRs)                │
│     AntiDebt/registry/known-debts.md   (debt-registry)       │
│     AntiDebt/logs/scan-{date}.md       (historique scans)    │
│     AntiDebt/dashboards/*.md           (Dataview queries)    │
└──────────────────────────────────────────────────────────────┘
```

## Conséquences

### Positives

- **Performance** : SQLite WAL mode supporte 10k+ writes/sec, queries causales O(log n) avec index
- **Concurrence** : SQLite WAL gère les accès concurrents (multi-lecteurs, 1-écrivain)
- **RAG** : le vault permet à n'importe quel agent LLM d'interroger l'historique en langage naturel
- **Backup** : snapshot SQLite quotidien → push vers vault → historique redondant
- **Dashboard** : Dataview génère des vues sans coder de frontend
- **Humain-first** : tout reste lisible dans Obsidian, pas de SQL à apprendre

### Négatives / Trade-offs

- **Double cohérence** : KG SQLite (source) ↔ vault markdown (vue) peuvent désynchroniser
  - Mitigation : `kg_sync.py` réconcilie périodiquement
  - Conséquence acceptée : SQLite = truth, vault = projection
- **Vault devient single point of failure** : si Obsidian down, pas d'interface humaine
  - Mitigation : les fichiers JSON dans `~/.mavis/findings/` restent lisibles directement
  - Le vault est un **bonus**, pas une dépendance critique
- **Coût stockage vault** : chaque snapshot KG peut faire plusieurs MB en markdown
  - Mitigation : snapshots delta (que les changements), pas full
- **Performance vault RAG** : 1000+ notes = RAG lent et coûteux
  - Mitigation : structure de dossiers stricte + tags de scoping
  - Dataview pré-agrège les KPIs chauds

## Schéma SQLite (kg.db)

```sql
-- Nœuds typés
CREATE TABLE nodes (
  id TEXT PRIMARY KEY,              -- UUID v4
  type TEXT NOT NULL,               -- 'Component' | 'Debt' | 'Decision' | 'Fix' | 'Convention' | 'ADR'
  name TEXT NOT NULL,
  metadata JSON,                    -- type-specific fields
  created_at TEXT NOT NULL,         -- ISO 8601
  updated_at TEXT NOT NULL
);

-- Arêtes typées
CREATE TABLE edges (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  type TEXT NOT NULL,               -- 'causes' | 'resolves' | 'conflicts' | 'supersedes' | 'affects' | 'blocks'
  metadata JSON,
  created_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES nodes(id),
  FOREIGN KEY (target_id) REFERENCES nodes(id)
);

-- Index pour queries causales
CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(type);
CREATE INDEX idx_nodes_type ON nodes(type);
```

## Format de projection vault

```markdown
---
kg_snapshot: 2026-06-17T12:00:00Z
node_count: 1247
edge_count: 3891
last_sync: 2026-06-17T11:55:00Z
---

# KG Snapshot — 2026-06-17

## By type
- Components: 423
- Debts: 87 (open: 23, resolved: 64)
- Decisions: 12 (accepted: 10, draft: 2)
- Fixes: 64
- Conventions: 5
- ADRs: 7

## Top 5 most-blocked components
[query KG]
```

## Migration V1 → V2

- V1 reste fonctionnel (fichiers JSON lus/écrits)
- `kg_migrate.py` lit V1 + écrit SQLite en arrière-plan
- V1 devient cache lecture seule
- V2 devient source de vérité

## Alternatives rejetées

- **JSON plat V1 amélioré** : pas scalable, problème fondamental
- **PostgreSQL** : dépendance externe, pas local-first
- **Vault Obsidian seul** : pas queryable, lent pour 10k+ nœuds
- **Neo4j** : sur-ingénierie pour le besoin, pas local-first
- **DuckDB** : excellent choix technique, mais moins de tooling de sync que SQLite

## Liens

- ADR-0017 (architecture V-max 7 couches)
- ADR-0019 (migration V1 → V2)
- ADR-0022 (versionning des schémas)
