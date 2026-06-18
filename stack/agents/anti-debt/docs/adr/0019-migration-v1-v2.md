# ADR-0019 — Migration Strategy V1 → V2

**Date** : 2026-06-17
**Statut** : Proposé
**Décideurs** : Erwan Barat, Mavis

## Contexte

L'agent V1 (livré 2026-06-17) utilise un modèle de stockage à base de fichiers JSON plats :
- `debt-history.json` (append-only)
- `debt-plan.json` (un par plan)
- `debt-scan.json` (un par scan)
- `examples/*.json` (fichiers d'exemple)

L'agent V2 introduit :
- KG SQLite (Layer 0)
- Debt Registry (`debt-registry.json` v2)
- Architecture 7 couches
- Skills `debt-architecture`, `debt-prevention`, `debt-manage`, `architecture-decision`, `debt-roadmap`

L'enjeu : migrer les utilisateurs existants (toi sur Seno) **sans rupture** et **sans perte d'historique**.

## Décision

**Migration en 3 phases avec période de coexistence** :

### Phase 1 — Dual-write (1-2 mois)

- V1 reste la source de vérité pour `debt-history.json`
- V2 commence à écrire dans SQLite en parallèle
- `kg_migrate.py` lit V1 + écrit V2 (one-shot, idempotent)
- Les deux formats coexistent, le critic lit les deux

### Phase 2 — Validation croisée (2-4 semaines)

- Chaque scan écrit dans V1 ET V2
- `kg_validator.py` compare les deux sorties
- Alerte si divergence (devrait être rare : SQLite = miroir du JSON)
- Statistique de cohérence publiée dans le vault

### Phase 3 — V1 lecture seule (dès 100% cohérence)

- V1 devient read-only (archive)
- V2 devient source de vérité
- `debt-history.json` peut être supprimé ou archivé dans `archive/v1/`
- Tous les nouveaux consumers lisent V2

## Conséquences

### Positives

- **Zéro perte d'historique** : V1 reste lisible jusqu'à validation complète
- **Rollback possible** : si V2 a un bug, on peut désactiver SQLite et retomber sur V1
- **Migration visible** : l'utilisateur voit la divergence si elle existe
- **Pas de big-bang** : on ship V1+V2 simultanément, on bascule progressivement

### Négatives / Trade-offs

- **Coût double-écriture** : 1.5x l'espace disque pendant la phase 1
  - Acceptable : V1 fait < 10MB même pour 100k LOC
- **Complexité du dual-format** : les consumers doivent lire les deux pendant la phase 2
  - Mitigation : adapter pattern `KgReader` qui abstrait la source

## Plan de migration concret

### Étape 1 — Création de l'outil de migration

```python
# kg_migrate.py
def migrate_v1_to_v2(v1_root: Path, kg_db: Path) -> MigrationReport:
    """Lit tous les fichiers V1 et les écrit dans SQLite V2.
    Idempotent : peut être ré-exécuté sans dupliquer.
    """
    # 1. Pour chaque .debt-scan.json : créer les nœuds Component, Debt
    # 2. Pour chaque .debt-history.json : créer les arêtes temporelles
    # 3. Pour chaque .debt-plan.json : créer les nœuds Decision
    # 4. Générer un rapport (X nodes, Y edges, Z warnings)
```

### Étape 2 — Dual-write dans le critic et les scanners

```python
# Avant (V1)
def save_findings(findings: list[dict], path: Path) -> None:
    path.write_text(json.dumps(findings))

# Après (V2)
def save_findings(findings: list[dict], path: Path, kg: KgStore) -> None:
    path.write_text(json.dumps(findings))  # V1 — backward compat
    kg.upsert_many(_findings_to_nodes(findings))  # V2 — source de vérité
```

### Étape 3 — Test de cohérence

```python
# kg_validator.py
def validate_consistency(v1_root: Path, kg_db: Path) -> ConsistencyReport:
    """Vérifie que SQLite V2 contient les mêmes findings que les JSON V1."""
    v1_findings = load_all_v1_findings(v1_root)
    v2_findings = kg.get_all_findings()
    diff = compare_findings(v1_findings, v2_findings)
    return ConsistencyReport(
        v1_count=len(v1_findings),
        v2_count=len(v2_findings),
        diff_count=len(diff),
        examples=diff[:10],
    )
```

### Étape 4 — Bascule V1 → V2 read-only

- Documentation dans le vault : "V1 est archivé, V2 est la source de vérité"
- Script `archive_v1.sh` qui déplace les fichiers V1 vers `archive/v1-{date}/`
- Garde-fou : V1 ne peut plus être modifié après l'archive

## Critères de succès migration

- [ ] `kg_migrate.py` exécuté avec succès sur un projet de test (e.g. fixture1-py-messy)
- [ ] 0 divergence entre V1 et V2 après migration
- [ ] Tous les consumers (skills, critic, hooks) lisent correctement V2
- [ ] Documentation utilisateur à jour
- [ ] `archive_v1.sh` testé sur un backup

## Risques

- **R1** : migration partielle si un fichier V1 est corrompu
  - Mitigation : transaction SQLite (tout ou rien), rapport explicite
- **R2** : consommateurs qui dépendent de l'ancien format
  - Mitigation : V1 reste lisible (read-only) pour 6 mois
- **R3** : utilisateurs qui n'ont pas lu la doc
  - Mitigation : CHANGELOG proéminent + alert dans le critic

## Liens

- ADR-0023 (storage)
- ADR-0017 (architecture)
- ADR-0022 (versionning)
