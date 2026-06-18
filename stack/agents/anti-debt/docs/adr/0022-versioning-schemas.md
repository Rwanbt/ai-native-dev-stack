# ADR-0022 — Backward Compatibility + Versioning des Schémas

**Date** : 2026-06-17
**Statut** : Proposé
**Décideurs** : Erwan Barat, Mavis

## Contexte

L'agent V1 utilise 3 schémas JSON Schema :
- `debt-finding.schema.json`
- `debt-plan.schema.json`
- `debt-history.schema.json`

L'agent V2 introduit :
- KG SQLite (schéma relationnel)
- Debt Registry v2 (CRUD)
- Feedback events schema
- ADR schema

Sans politique de versioning, chaque changement casse les consumers existants.

## Décision

**Politique de versioning = SemVer strict + migrations versionnées** :

### Niveau 1 — Schémas JSON Schema versionnés

Chaque schéma a :
- Champ `$id` = URL canonique (unique, immutable)
- Champ `$schema` = version JSON Schema utilisée
- Champ `version` (custom) = SemVer du schéma lui-même

```json
{
  "$id": "https://ai-native-dev-stack/schemas/debt-finding.schema.json",
  "$schema": "http://json-schema.org/draft-07/schema#",
  "version": "1.0.0",
  "title": "DebtFinding",
  ...
}
```

### Niveau 2 — SemVer appliqué aux schémas

- **MAJOR** (1.x.x → 2.x.x) : breaking changes (suppression de champ, renommage required)
- **MINOR** (x.1.x → x.2.x) : ajout de champ optionnel, nouveau enum value
- **PATCH** (x.x.1 → x.x.2) : clarification de description, pas de changement structurel

**Règle** : un consumer qui supporte schema 1.x doit pouvoir lire un fichier schema 1.x sans modification.

### Niveau 3 — Migrations explicites

Pour chaque MAJOR bump, un script de migration :

```
tools/migrations/
├── 1.0.0_to_1.1.0_add_field_x.py
├── 1.1.0_to_2.0.0_rename_field_y.py
└── _registry.json     (mapping version → migration script)
```

Chaque migration :
- Lit l'ancien format
- Écrit le nouveau format
- Idempotente (peut être ré-exécutée)
- Testée sur des fixtures round-trip

### Niveau 4 — Dépréciation policy

- Un schema en MAJOR N reste supporté **6 mois** après la sortie de N+1
- Pendant cette période, un warning est émis à la lecture
- Après 6 mois, le MAJOR N-1 peut être supprimé (avec annonce dans CHANGELOG)

### Niveau 5 — SQLite KG schema migrations

Le KG SQLite a son propre mécanisme de migration :

```python
# kg_migrate.py
class KgMigrator:
    """Applique les migrations séquentiellement au KG SQLite."""

    def __init__(self, kg_db: Path):
        self.conn = sqlite3.connect(kg_db)
        self._ensure_migration_table()

    def _ensure_migration_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)

    def migrate(self, target_version: str) -> MigrationResult:
        applied = self._get_applied_versions()
        pending = self._get_pending_migrations(target_version, applied)
        for migration in pending:
            self._apply_migration(migration)
        return MigrationResult(applied=len(pending))
```

Inspirated by Alembic / Flyway / sqlx-migrate.

## Conséquences

### Positives

- **Évolutivité safe** : on peut changer les schémas sans casser les consumers
- **Traçabilité** : chaque migration est loggée, on sait quand et pourquoi un changement
- **Rollback possible** : si une migration V2 casse, on peut downgrader vers V1
- **Idempotence** : ré-exécuter une migration n'a pas d'effet de bord

### Négatives / Trade-offs

- **Complexité de maintenance** : 1 fichier de migration par MAJOR bump
  - Acceptable : c'est ce que font tous les ORMs modernes
- **Tests de round-trip** obligatoires pour chaque migration
  - Acceptable : c'est une bonne pratique qui force à tester les chemins de migration

## Exemples de migrations

### Exemple 1 — Ajout d'un champ optionnel (MINOR 1.0.0 → 1.1.0)

```python
# tools/migrations/1.0.0_to_1.1.0_add_reviewed_by.py
def up(findings: list[dict]) -> list[dict]:
    for f in findings:
        f.setdefault("reviewed_by", None)
    return findings

def down(findings: list[dict]) -> list[dict]:
    for f in findings:
        f.pop("reviewed_by", None)
    return findings
```

### Exemple 2 — Renommage d'un champ required (MAJOR 1.x → 2.0)

```python
# tools/migrations/1.1.0_to_2.0.0_rename_severity.py
SEVERITY_MAPPING = {
    "low": "info",
    "medium": "warning",
    "high": "error",
    "critical": "fatal",
}

def up(findings: list[dict]) -> list[dict]:
    for f in findings:
        if "severity" in f:
            f["severity"] = SEVERITY_MAPPING.get(f["severity"], f["severity"])
    return findings
```

## Critères d'acceptation

- [ ] Chaque schéma JSON Schema a un champ `version`
- [ ] Chaque MAJOR bump a un script de migration + tests round-trip
- [ ] `kg_migrate.py` testé sur fixtures (old version → new version → assertions)
- [ ] Documentation : comment marquer un schema comme deprecated

## Liens

- ADR-0023 (storage)
- ADR-0019 (migration V1 → V2)
