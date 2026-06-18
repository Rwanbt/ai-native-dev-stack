# ADR-0024 : Pipeline Layer 4-7 (orchestration, self-update, UI)

**Date** : 2026-06-17 | **Statut** : Accepté | **Auteur** : Mavis

## Contexte

L'ADR-0017 a défini l'architecture 7+1 couches. Les Layers 0-3 sont implémentés et testés (76/76 tests verts). Les Layers 4-7 complètent le pipeline pour passer d'un agent de scan ponctuel à un système autonome de gestion de dette technique.

## Décision

Implémenter 3 modules complémentaires (Layer 4, 6, 7) qui ferment la boucle :

### Layer 4 — Orchestration multi-projet (`tools/scan_periodic.py`)

- Lit un `projects.json` qui liste les projets à scanner (path, layers activées, alertes)
- Boucle configurable (`--once` ou `--interval <seconds>`)
- Chaque tour : scan → persist dans KG → alertes si critical/high
- Sortie : `tools/scan_periodic_report.json` + `alerts.log` (toujours disponible) + Telegram (optionnel via env)

### Layer 6 — Self-update (`tools/calibration.py`)

- Lit `.debt-history.json` (overrides humaines)
- Groupe par bucket de confidence ([0-0.4, 0.4-0.7, 0.7-0.9, 0.9-1.0])
- Calcule une proxy-precision par bucket
- Propose de nouveaux seuils `reject_below` et `review_below` si precision < 90%
- Sortie : `calibration_report.md` + `critic_config.json` (si `--apply`)

### Layer 7 — Dashboard HTML (`tools/dashboard.py`)

- Lit `kg/data/kg.db` (SQLite)
- Génère un fichier HTML statique self-contained (SVG natif, pas de JS framework)
- Affiche : KPIs, distribution severity/category, top files, components, 20 debts les plus récents
- Sortie : `tools/dashboard.html` (~11 KB)

## Alternatives rejetées

- **Layer 5 ML** (prédiction de dette future via modèle) : trop ambitieux pour cette itération. Reporté à V2.
- **Mode MVP runtime automatisé** : orchestration de bout en bout des 6 skills (scan → plan → fix → verify). Nécessite un agent d'orchestration LLM séparé.
- **CLI riche (`mavis anti-debt scan/plan/fix/...`)** : plus de valeur via le dashboard HTML + appel direct des scripts Python.

## Conséquences

### Avantages
- 76/76 tests verts (22 + 14 + 23 + 17) : pipeline complet testé bout en bout
- Score scan_quality : 87.5% precision, 100% recall (targets 80/70% battus)
- Self-update loop activable : l'agent apprend des overrides sans intervention
- Dashboard visualisable offline, sans serveur

### Inconvénients
- Pas de Layer 5 (ML) — la prédiction est un nice-to-have, pas critique pour la V1
- Le dashboard n'est pas interactif (pas de drill-down) — c'est un report statique
- scan_periodic nécessite un cron/launchd externe pour tourner en arrière-plan

## Conditions d'acceptance (toutes remplies)

- [x] 76/76 tests verts
- [x] scan_periodic scanné 2 projets réels sans crash
- [x] KG alimenté : 215 debts, 215 edges
- [x] Dashboard généré en < 1s, 11 KB
- [x] Calibration report fonctionnel sur history synthétique

## Suite

- [ ] Layer 5 ML : entraîner un modèle sur les overrides réelles
- [ ] cron job / Windows Task Scheduler pour scan_periodic
- [ ] Mode MVP runtime (orchestrateur des 6 skills)
- [ ] CI integration : ajouter tests layer47 dans anti-debt-ci.yml
