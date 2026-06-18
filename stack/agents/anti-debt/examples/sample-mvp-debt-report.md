# MVP Debt Report — Example Project

**Date** : 2026-06-17
**Statut** : Dette MVP acceptée explicitement par l'utilisateur
**Scan source** : scan-2026-06-17-002

## 1. Contexte

L'utilisateur a demandé un MVP rapide pour la fonctionnalité "export CSV".
Citation : *"Livre-moi ça en MVP, on en parlera après la démo client de mardi."*

## 2. Raccourcis pris

1. ❌ Pas de tests unitaires sur la sérialisation CSV
2. ❌ Pas de validation des entrées utilisateur (champs requis, format)
3. ❌ Pas de gestion d'erreur explicite (encodage manquant, fichier ouvert ailleurs, etc.)
4. ❌ Pas de logging de l'opération (audit trail)
5. ❌ Pas de rate limiting sur l'endpoint
6. ❌ Code dupliqué depuis `export_json()` (~40 LOC copiées-collées)
7. ❌ Pas de documentation API (OpenAPI/Swagger)

## 3. Dette introduite

### Catégorie `code`
- **f-mvp-001** : duplication (medium) — `export_csv()` duplique `export_json()`
- **f-mvp-002** : error_handling (medium) — pas de try/except sur la sérialisation

### Catégorie `tests`
- **f-mvp-003** : coverage_gaps (high) — 0% de couverture sur le nouveau code
- **f-mvp-004** : missing_integration (medium) — pas de test E2E

### Catégorie `security`
- **f-mvp-005** : unsafe_io (high) — injection CSV possible via caractères spéciaux non échappés

## 4. Risques immédiats (DOIVENT être fixés avant production)

- **f-mvp-005** : injection CSV — risque de sécurité, fix requis avant exposition publique
- **f-mvp-003** : aucune couverture — risque de régression silencieuse

## 5. Plan de résorption

| Action | Finding | Effort | Dépendances |
|--------|---------|--------|-------------|
| Extraire helper de sérialisation partagé | f-mvp-001 | 1j | - |
| Ajouter validation entrées | - | 1j | - |
| Ajouter try/except + messages explicites | f-mvp-002 | 0.5j | - |
| Échapper caractères spéciaux CSV | f-mvp-005 | 0.5j | - |
| Tests unitaires export_csv | f-mvp-003 | 1j | helper |
| Test E2E export endpoint | f-mvp-004 | 1j | helper, validation |

**Effort total** : ~5 jours-homme
**Deadline cible** : 2026-07-15 (4 semaines)

## 6. Métriques de suivi

- [ ] Coverage `export_csv()` ≥ 80% (baseline: 0%)
- [ ] 0 findings `code.duplication` dans le module export (baseline: 1)
- [ ] Aucun `unsafe_io` dans `export_csv()` (baseline: 1)
- [ ] Au moins 1 test E2E pass pour `/api/export/csv` (baseline: 0)
