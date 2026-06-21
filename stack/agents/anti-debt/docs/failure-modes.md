# Failure Modes — Anti-Debt Agent

> **Date** : 2026-06-21
> **Statut** : V1 — inventaire initial, à enrichir avec les données de production
> **Objectif** : Cataloguer tous les modes de défaillance connus pour orienter les evals et le calibrage

---

## FM-01 : Faux positifs (bruit)

**Impact** : Érode la confiance utilisateur. Si >30% des findings sont des FP, l'outil est ignoré.

| Sous-type | Trigger | Exemple | Test couvrant |
|-----------|---------|---------|---------------|
| `complexity_false_alarm` | Seuil CC trop bas pour du code data-heavy (match/switch) | Un parser avec 20 branches légitimes flaggé god_class | `test_layer12.py` (CC calculation) |
| `stale_dependency_flag` | osv-scanner détecte un CVE qui ne s'applique pas (feature non utilisée) | CVE sur une feature optionnelle de `serde` non activée | `test_scan_quality.py` (precision gate) |
| `test_coverage_phantom` | Coverage tool compte les lignes de config/types comme non couvertes | `#[derive(...)]` dans Rust compté comme uncovered | Pas de test spécifique — **TODO** |
| `naming_noise` | Scanner de style flag des conventions de domaine légitimes (DSP: `fft`, `db`, `lfo`) | Variable `q` dans un filtre biquad = convention audio universelle | Pas de test — **TODO: allowlist domaine** |

**Métrique de suivi** : `reject_override_rate` dans calibration.py (bucket [0.7-0.9])

---

## FM-02 : Faux négatifs (angles morts)

**Impact** : Dette cachée qui s'accumule silencieusement. Pire que les FP car invisible.

| Sous-type | Cause racine | Exemple | Test couvrant |
|-----------|-------------|---------|---------------|
| `no_scanner_for_category` | Taxonomie couvre architecture/observability mais pas de scanner implémenté | God-class de 3000 LOC jamais détecté car `scan_architecture.py` ne check pas la taille | `test_no_mvp_regression.py` (scope completeness) |
| `threshold_too_high` | Seuil de détection exclut des cas réels | CC=14 non flaggé car seuil à 15 | `test_layer12.py` (seuils codés en dur) |
| `language_blind_spot` | Scanner Python-only sur un projet polyglot | Fichiers `.rs` ignorés par `scan_code.py` si pas de config Rust | `test_scan_quality.py` (coverage par fixture) |
| `temporal_blind_spot` | Pas de diff-based detection — ne voit que l'état actuel | Régression introduite par un commit récent noyée dans le bruit existant | Partiellement couvert par `findings_regressed` dans history |

**Métrique de suivi** : `findings_regressed` dans `.debt-history.json` + recall par catégorie

---

## FM-03 : Hallucinations du Critic

**Impact** : Un finding accepté sur la base d'evidence fabriquée = action incorrecte.

| Sous-type | Mécanisme | Garde en place | Test couvrant |
|-----------|-----------|----------------|---------------|
| `self_referential_evidence` | Finding cite son propre ID comme evidence | Critic rejette (policy codée) | `test_critic_blocks_hallucinations.py` |
| `confidence_inflation` | LLM assigne confidence=0.95 sans base factuelle | Critic tier system (0.6 floor) | `test_no_mvp_regression.py` |
| `circular_justification` | Description reprend verbatim l'evidence value | Pas de garde — **TODO: similarity check** | Aucun |
| `phantom_file_reference` | Evidence pointe vers un fichier qui n'existe pas | Pas de garde runtime — **TODO: path validation** | Aucun |

**Métrique de suivi** : `override_rate` global dans calibration stats (kill switch à 30%)

---

## FM-04 : Drift de calibration

**Impact** : Les seuils deviennent inadaptés au fil du temps, accept trop ou trop peu.

| Sous-type | Mécanisme | Garde en place | Test couvrant |
|-----------|-----------|----------------|---------------|
| `permissive_drift` | Trop d'accept_overrides → seuils baissent → bruit augmente | `calibration.py` propose mais n'applique pas sans --apply | `test_layer47.py` (threshold proposal) |
| `restrictive_drift` | Trop de reject_overrides → seuils montent → angles morts | Warning si bucket [0.9-1.0] precision < 90% | `test_layer47.py` (warning generation) |
| `insufficient_data` | Propositions basées sur <5 overrides par bucket = statistiquement invalide | Guard `total > 5` avant proposition | `test_layer47.py` (no-history handling) |

**Métrique de suivi** : `kill_switch_triggered` dans calibration stats

---

## FM-05 : Régression silencieuse

**Impact** : Un changement de scanner/seuil dégrade la qualité sans alerter.

| Sous-type | Mécanisme | Garde en place | Test couvrant |
|-----------|-----------|----------------|---------------|
| `scanner_interference` | Nouveau scanner overlap avec un existant → dupliques ou contradictions | Pas de garde — **TODO: dedup cross-scanner** | Aucun |
| `recall_drop` | Modification de seuil dans un scanner réduit recall sur les fixtures | Recall ≥ 70% enforced en CI | `test_scan_quality.py` |
| `precision_drop` | Nouveau pattern de détection génère des FP massifs | Precision ≥ 60% enforced en CI | `test_scan_quality.py` |

**Métrique de suivi** : `avg_precision` et `avg_recall` dans CI (hard gates)

---

## FM-06 : Context poisoning (historique)

**Impact** : Un finding erroné persisté en historique influence les triages futurs.

| Sous-type | Mécanisme | Garde en place | Test couvrant |
|-----------|-----------|----------------|---------------|
| `stale_finding_persists` | Finding résolu mais jamais marqué resolved → pèse dans debt_delta | `findings_resolved` array dans history | Pas de test de propagation — **TODO** |
| `wrong_severity_propagated` | Finding high↔critical mal classé, jamais corrigé, sert de baseline | Override enregistré avec reason mais pas de re-score auto | Aucun |
| `ghost_category` | Catégorie renommée dans taxonomy mais anciens findings gardent l'ancien nom | Schema enum validation | `test_schema_conformance.py` |

**Métrique de suivi** : `debt_delta` incohérent (négatif malgré pas de fix = symptôme)

---

## Matrice de couverture

| Failure Mode | Tests existants | Métriques trackées | Evals LLM-as-judge | Actions TODO |
|---|---|---|---|---|
| FM-01 FP | ✅ precision gate | ✅ reject_override_rate | ❌ Livrable 2 | Allowlist domaine |
| FM-02 FN | ✅ recall gate | ⚠️ partiel (regressed) | ❌ Livrable 2 | Scanner architecture LOC |
| FM-03 Hallucinations | ✅ critic policy | ✅ override_rate | ❌ Livrable 2 | Path validation, similarity |
| FM-04 Drift | ✅ calibration tests | ✅ kill_switch | ❌ | — |
| FM-05 Régression | ✅ CI precision/recall | ✅ CI pass/fail | ❌ | Dedup cross-scanner |
| FM-06 Poisoning | ⚠️ schema only | ⚠️ debt_delta | ❌ Livrable 2 | Propagation test |

---

## Processus d'enrichissement

1. Quand un override est enregistré → classifier dans quel FM il tombe
2. Quand un bug agent est découvert → ajouter un sous-type ici + créer un test
3. Trimestriellement : revoir la matrice de couverture, prioriser les TODO
