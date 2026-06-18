# Scoring Calibration — Anti-Dette Agent

> **Date** : 2026-06-17
> **Statut** : V1.2 — calibration empirique du score `(impact × urgence × confidence) / effort`
> **Auteur** : Mavis (orchestrateur)

---

## 1. Pourquoi cette doc existe

La formule de scoring `(impact × urgence × confidence) / effort` est **cosmétique** tant qu'elle n'est pas calibrée empiriquement. Sans calibration :

- Les 5 findings "critical" d'un scan apparaissent tous avec un score élevé sans distinction
- Un reviewer ne peut pas prioriser objectivement
- Le "fix this first" devient arbitraire

Cette doc :
1. Documente les valeurs par défaut
2. Donne un protocole de calibration empirique reproductible
3. Permet d'ajuster sans casser les findings déjà historisés

---

## 2. Variables du score

### Impact (entier 1-4)

| Valeur | Sévérité | Définition opérationnelle |
|--------|----------|--------------------------|
| 4 | critical | Le code ne doit pas tourner en production. Secret leak, RCE, crash, data loss. |
| 3 | high | Bug probable ou dette qui va bloquer une feature à court terme. |
| 2 | medium | Dette qui dégrade la maintenabilité, la perf, ou la lisibilité. |
| 1 | low | Cosmétique. Style, doc manquante, naming. |

**Pas de 0** — une finding sans impact n'est pas un finding.

### Urgence (entier 1-4, défaut = impact)

| Valeur | Définition |
|--------|------------|
| 4 | Maintenant — bloque la release courante ou cause un incident actif. |
| 3 | Cette semaine — feature à livrer dans 1-2 semaines, dette va bloquer. |
| 2 | Ce mois — dans la roadmap actuelle, dette pas bloquante. |
| 1 | Plus tard — backlog, peut attendre 3+ mois. |

**Override possible** : si l'urgence diffère de l'impact (ex: dette critique mais on a 6 mois), l'urgence override. **Toujours documenter l'override dans `metadata.urgency_reason`.**

### Confidence (float 0.0-1.0)

Calibré par **le tool source**, mappé sur les 3 tiers du Critic Engine
(`reject < 0.6` ≤ `review < 0.7` ≤ `accept`) :
- **1.0** : finding déterministe, pas de doute (regex match, AST metric, type checker error) → **accept**
- **0.9** : heuristique forte (python-ast fallback, 2+ signaux concordants) → **accept**
- **0.7-0.8** : heuristique faible (1 seul signal, possible faux positif) → **accept**
- **0.6-0.7** : revue humaine requise (LLM-only finding, classification ambiguë) → **review**
- **< 0.6** : **rejeté** par le Critic Engine (threshold non-négociable, cf. [critic_v2.py](../tools/critic_v2.py) `TIER_REJECT`)

Voir [[D:\App\ai-native-dev-stack\stack\agents\anti-debt\docs\adr\0021-critic-self-challenge|ADR-0021]].

### Effort (estimé en jours-personnes, float)

| Code | Estimation | Définition |
|------|------------|------------|
| XS | 0.05 (≈30 min) | 1 ligne, 1 fichier, pas de test à écrire |
| S  | 0.25 (≈2h) | Quelques lignes, 1-2 fichiers, 1 test |
| M  | 1 | 1 fichier ou petit refactor, quelques tests |
| L  | 3 | Multi-fichiers, refactor non-trivial, tests d'intégration |
| XL | 10+ | Refactor architectural, migration, nouveau module |

**Pas d'effort = 1 par défaut** — laisse le score bas pour les dettes dont l'effort n'est pas estimé.

---

## 3. Formule finale

La formule autoritative est celle implémentée dans [critic_v2.py](../tools/critic_v2.py)
(`compute_score`) et verrouillée par `tests/test_layer12.py`. Le `risk_multiplier`
pénalise les fixes risqués (un fix dangereux à effort égal descend dans la file) :

```
effective_effort = max(effort_days × risk_multiplier, 0.1)
score            = (impact × urgence × confidence) / effective_effort
```

Avec `risk_multiplier` = {low: 1.0, medium: 1.5, high: 2.5} et `effort_days` =
{XS: 0.05, S: 0.25, M: 1.0, L: 3.0, XL: 10.0}.

**Interprétation** (bandes indicatives — un `critical/S/low-risk` ≈ 64, cf. `test_score_critical_high`) :
- `score > 50` : **P0** — fix cette semaine
- `20 < score ≤ 50` : **P1** — ce mois
- `5 < score ≤ 20` : **P2** — ce trimestre
- `score ≤ 5` : **P3** — backlog

---

## 4. Calibration empirique — protocole

### Source de données : `.debt-history.json`

Chaque finding a un historique qui track :
- Quand elle a été détectée
- Quand elle a été fixée (`resolved_at`)
- L'effort réel investi (`actual_effort_days`)
- Le coût de NE PAS l'avoir fixée (combien de fois on l'a touchée, bugs incidents, etc.)

### Étape 1 — Collecter 30+ fixes réels

Pour calibrer, on a besoin de **minimum 30 findings fixées** avec :
- `actual_effort_days` (mesuré)
- `impact_at_resolution` (à 1-4, révisé si on s'est trompé)
- `was_correct_priority` (boolean — on a bien choisi ?)

**Source** : un projet réel instrumenté sur 1-2 mois. Pas le repo courant (trop petit), un projet comme Seno, HireLens, ou VECTORA.

### Étape 2 — Calculer la corrélation

Pour chaque finding fixée, on calcule :
```python
predicted_score = (impact_pred × urgence × confidence) / effort_pred
actual_score   = (impact_actual × urgence × confidence) / actual_effort_days
ratio = actual_score / predicted_score
```

Idéalement, `median(ratio) ≈ 1.0` et `IQR(ratio) < 0.5`.

### Étape 3 — Ajuster les poids

Si la médiane des ratios est systématiquement > 1.5, on sous-estime l'impact → augmenter la valeur de `critical` à 5.

Si l'IQR est trop large (> 1.0), ajouter une variable (ex: `risk_of_fix` qui pénalise les fixes risqués).

### Étape 4 — Re-scoring rétroactif

Quand on change la calibration, on DOIT re-scorer les findings historiques :
- Pas de modification des findings (immuable)
- Ajout d'un champ `recalibrated_score` à côté de `score`
- Le dashboard utilise `recalibrated_score` pour la tri

---

## 5. Calibration initiale V1.2 (par défaut)

Sans données empiriques (état actuel), on utilise les valeurs documentées section 2.

**Hypothèse forte** : la calibration initiale sur-estime l'impact (biais LLM = "tout est urgent"). Le Critic Engine compense via le confidence threshold à 0.6.

**Validation prévue** : après 30+ findings fixées sur un projet réel, recalibrer. Cible : 3-6 mois de dogfooding.

---

## 6. Limites connues

- **Subjectivité de l'impact** : 2 reviewers peuvent classer différemment. Solution : ADR-0021 propose "calibration empirique depuis feedback".
- **Effort sous-estimé** : pattern classique (estimé 1j, réel 3j). Déjà pondéré par `risk_of_fix` ∈ {low, medium, high} via le `risk_multiplier` {1.0, 1.5, 2.5} de la formule §3. Ajustement futur possible : calibrer ces multiplicateurs sur l'effort réel observé (`actual_effort_days`).
- **Confidence biaisé vers 0.9** : les tools déterministes marquent 1.0, l'heuristique 0.9. L'écart est trop faible pour distinguer "regex match parfait" de "AST best-effort". Solution V2 : confidence à 2 dimensions (`{precision, recall}`).

---

## 7. Tests à écrire (V1.3)

- [ ] `test_scoring_monotonic.py` : impact plus haut → score plus haut (sanity check)
- [ ] `test_scoring_effort_inverse.py` : effort plus haut → score plus bas
- [ ] `test_scoring_priority_tiers.py` : 5 findings synthetic, P0/P1/P2/P3 corrects
- [ ] `test_scoring_confidence_threshold.py` : confidence 0.5 → score réduit de 50%
- [ ] `test_scoring_override.py` : urgence != impact documenté dans metadata

---

## 8. Références

- [[D:\App\ai-native-dev-stack\stack\agents\anti-debt\docs\adr\0021-critic-self-challenge|ADR-0021]] — Critic Engine (threshold 0.6, calibration empirique)
- [[D:\App\ai-native-dev-stack\stack\agents\anti-debt\docs\adr\0022-versioning-schemas|ADR-0022]] — Versioning (recalibration doit être rétrocompatible)
- `schemas/debt-finding.schema.json` — champs impact/urgency/confidence/effort
- `taxonomy/debt-categories.yaml` — `severity_defaults` (impact par défaut par category)
