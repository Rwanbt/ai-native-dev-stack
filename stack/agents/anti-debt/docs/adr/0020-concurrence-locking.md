# ADR-0020 — Concurrence + Locking Model

**Date** : 2026-06-17
**Statut** : Proposé
**Décideurs** : Erwan Barat, Mavis

## Contexte

L'agent V-max peut être invoqué par plusieurs sessions en parallèle :
- Mavis en background
- Claude Code dans une autre fenêtre
- Une CI job qui scan sur chaque PR
- Un cron de recalibrage

Sans coordination, deux écritures concurrentes peuvent :
- Corrompre le KG SQLite (last-write-wins, perte de données)
- Désynchroniser le vault (snapshots incohérents)
- Faire diverger le scoring (deux recalibrages en parallèle)

## Modélisation des scénarios de concurrence

### Scénario 1 — Deux scans simultanés

```
Session A : scan_code.py sur /repo
Session B : scan_code.py sur /repo
→ Deux fichiers .debt-scan.json produits
→ Si l'un écrase l'autre, on perd un scan
```

### Scénario 2 — Scan + fix simultanés

```
Session A : debt-scan (lecture + écriture)
Session B : debt-fix (lecture + écriture du fix)
→ Risque : le fix s'appuie sur des findings que A est en train de re-écrire
```

### Scénario 3 — Recalibrage + scan

```
Session A : feedback_loop.py (recalcule le scoring)
Session B : scan (utilise l'ancien scoring)
→ Inconsistance temporaire mais pas de corruption
```

### Scénario 4 — Promotion pattern + scan

```
Session A : promote_pattern.py (ajoute un nouveau skill)
Session B : scan (utilise l'ancien skill set)
→ Acceptable : le skill n'existait pas au moment du scan
```

## Décision

**Modèle de concurrence = SQLite WAL + advisory locks + file d'attente** :

### Niveau 1 — SQLite WAL (Write-Ahead Logging)

SQLite en mode WAL gère nativement :
- **Multi-lecteurs** simultanés (les scans lisent en parallèle)
- **1 écrivain** à la fois (les updates sont sérialisés)
- **Lectures non bloquantes** : un scan peut lire pendant qu'un fix écrit

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;  -- 5 secondes d'attente si lock
```

### Niveau 2 — Advisory locks par opération

Pour les opérations longues (scan, fix, recalibrage), un advisory lock au niveau du KG :

```python
# kg_lock.py
import sqlite3

class KgLock:
    def __init__(self, kg_db: Path, operation: str, timeout: int = 30):
        self.conn = sqlite3.connect(kg_db)
        self.operation = operation
        self.timeout = timeout

    def __enter__(self):
        # SQLite ne supporte pas les advisory locks natifs, mais on
        # peut utiliser un lock table avec busy_timeout
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                self.conn.execute("BEGIN EXCLUSIVE")
                return self
            except sqlite3.OperationalError as e:
                if "locked" in str(e):
                    time.sleep(0.5)
                else:
                    raise
        raise TimeoutError(f"Could not acquire lock for {self.operation}")

    def __exit__(self, *args):
        self.conn.execute("COMMIT")
        self.conn.close()
```

### Niveau 3 — File d'attente pour les opérations lourdes

Les opérations qui peuvent prendre > 5 secondes passent par une queue :

```python
# kg_queue.py
class KgQueue:
    """File d'attente persistante pour les opérations lourdes."""

    def submit(self, op_type: str, op_payload: dict) -> str:
        """Retourne un job_id."""
        ...

    def wait(self, job_id: str, timeout: int = 300) -> JobResult:
        """Attend la fin du job."""
        ...
```

Opérations concernées :
- `recalibrate_scoring` (lit tout le feedback, recalcule)
- `promote_pattern` (analyse les findings, crée un skill)
- `kg_sync_to_vault` (snapshot complet + push)
- `bootstrap_kg` (premier scan + init)

### Niveau 4 — Idempotence

Toutes les opérations sont idempotentes :
- Un scan exécuté 2 fois = même résultat
- Un fix appliqué 2 fois = pas de double-application
- Un snapshot 2 fois = pas de corruption

Implémenté via :
- UUID v4 sur chaque finding/fix
- UPSERT (INSERT OR REPLACE) en SQL
- Check-before-act pour les patches fichiers

## Conséquences

### Positives

- **SQLite WAL est battle-tested** : utilisé par Chrome, Firefox, iOS
- **Coût minimal** : pas de Redis, pas de Postgres, pas de Kafka
- **File d'attente locale** : survit aux redémarrages (table SQLite)
- **Idempotence** : permet les retries sans état corrompu

### Négatives / Trade-offs

- **1 seul écrivain SQLite à la fois** : bottleneck sur les updates concurrents
  - Acceptable : SQLite WAL tient > 10k writes/sec, suffisant pour usage dev
- **File d'attente ajoute de la latence** : un recalibrage peut prendre 1-2 min
  - Acceptable : c'est une opération lourde de toute façon
- **Advisory locks en SQLite sont limités** : on doit simuler avec des transactions exclusives
  - Mitigation : timeout 5s + retry + queue fallback

## Critères d'acceptation

- [ ] Test : 10 sessions concurrentes peuvent scanner sans corruption
- [ ] Test : 2 sessions qui essaient de fixer le même finding → 1 succès, 1 erreur claire
- [ ] Test : kill -9 d'une session pendant un write → KG intègre au recovery
- [ ] Test : file d'attente persiste après redémarrage

## Liens

- ADR-0023 (storage)
- ADR-0017 (architecture)
