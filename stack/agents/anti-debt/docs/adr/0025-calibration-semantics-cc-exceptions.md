# ADR-0025 — Sémantique de calibration (raise/lower) + exceptions de complexité cyclomatique

**Date** : 2026-06-19
**Statut** : Accepté
**Décideurs** : Erwan Barat, Claude

## Contexte

Deux points restaient implicites dans le code après le durcissement de l'agent
anti-dette (PR #6, #7) :

1. **Le sens des ajustements de seuils du Critic** (`calibration.py`). La fonction
   `propose_thresholds()` baisse les seuils dans certains cas et ne les remonte
   jamais automatiquement. Ce comportement asymétrique est intentionnel mais
   n'était documenté nulle part — un futur contributeur pourrait « corriger » ce
   qu'il prend pour un bug et introduire une boucle d'instabilité.

2. **Deux fonctions dépassent le seuil de complexité cyclomatique (CC ≤ 10)** que
   l'agent impose lui-même : `static_analysis.analyze_file()` et
   `polyglot_scan.detect_js_cycles()`. L'agent se scanne lui-même (dogfooding) ;
   sans décision actée, ces deux findings reviennent à chaque scan et polluent le
   rapport.

## Décision

### 1. Sémantique de calibration — baisser oui, remonter non (automatiquement)

`calibration.py` lit l'historique des overrides humains, regroupe par bucket de
confiance, calcule un *precision proxy* par bucket, et propose de nouveaux seuils
`reject_below` / `review_below`. La règle est **asymétrique et conservatrice** :

| Situation observée | Action proposée | Direction |
|---|---|---|
| Bucket bas `[0.0–0.4]` peu précis (proxy < 0.90, n > 5) | `reject` 0.6 → 0.5 | **baisser** |
| Bucket mid `[0.4–0.7]` peu précis (proxy < 0.90, n > 5) | `review` 0.7 → ~proxy+0.1 | **baisser** |
| Bucket haut `[0.9–1.0]` peu précis | **WARNING uniquement**, aucun changement | — |
| Données insuffisantes (n ≤ 5) ou bien calibré | « No change » | — |

**Pourquoi on ne remonte jamais automatiquement un seuil :**

- Remonter `reject` = laisser passer *plus* de findings vers la revue humaine.
  Un Critic qui s'auto-relâche sur la base d'un feedback biaisé (humain fatigué
  qui confirme tout) deviendrait un *rubber-stamp* : c'est précisément le drift
  contre lequel l'agent est censé protéger (cf. ADR-0021, risque #5).
- Baisser un seuil est **réversible et visible** : ça génère plus de bruit, donc
  plus de signal de feedback, donc une auto-correction rapide. Remonter est
  **silencieux et dangereux** : moins de findings = moins de feedback = pas de
  signal d'auto-correction. L'asymétrie est volontaire.
- Le garde `n > 5` par bucket et le plancher `max(0.2, …)` empêchent une
  sur-réaction sur peu de données ou un effondrement du seuil.

**Conséquence opérationnelle** : remonter un seuil reste possible mais **exige une
décision humaine explicite** (éditer `critic_config.json` à la main, ou un futur
ADR). `calibration.py --apply` ne remontera jamais un seuil tout seul.

> Invariant à préserver : `calibration.DEFAULT_REJECT` / `DEFAULT_REVIEW` doivent
> rester synchronisés avec `critic_v2.TIER_REJECT` / `TIER_REVIEW` (0.6 / 0.7).

### 2. Exceptions CC documentées — deux parsers séquentiels

Le CLAUDE.md global tolère explicitement les **parsers séquentiels linéaires**
comme exception au plafond CC ≤ 10. Les deux fonctions suivantes sont actées
comme exceptions permanentes :

| Fonction | Fichier | Raison |
|---|---|---|
| `analyze_file()` | `tools/static_analysis.py:122` | Parcours AST Python unique : un `if isinstance(node, …)` par type de nœud (FunctionDef, ClassDef, Import…). Découper en sous-fonctions par type *augmenterait* le couplage (chaque sous-fonction re-walk l'arbre ou partage un état mutable) sans gain de lisibilité. |
| `detect_js_cycles()` | `tools/polyglot_scan.py:289` | Parser regex + construction de graphe + DFS de détection de cycles en une passe. La CC vient de la résolution d'imports JS/TS (extensions multiples, index, relatif/absolu) — séquence linéaire de cas, pas une logique métier imbriquée. |

Ces deux fonctions portent un commentaire `# CC-EXCEPTION: see ADR-0025` sur leur
ligne `def`. Tout *nouveau* dépassement de CC reste un finding à corriger : cette
exception ne couvre que ces deux parsers nommés, pas une dispense générale.

## Alternatives rejetées

- **Calibration symétrique (remonter auto les seuils)** : rejetée — réintroduit
  le drift rubber-stamp que l'agent doit prévenir.
- **Refactorer les deux parsers pour passer sous CC ≤ 10** : rejetée — découper un
  parcours AST/graphe en une passe en sous-fonctions augmente le couplage et le
  risque de bug pour un gain cosmétique. La norme prévoit déjà cette exception.
- **Supprimer la règle CC du self-scan** : rejetée — on perdrait la détection des
  *vrais* dépassements futurs.

## Conséquences

- **Positif** : le comportement asymétrique de calibration est désormais une
  décision tracée, pas un accident ; un contributeur ne le « corrigera » plus.
- **Positif** : les deux findings CC du self-scan sont actés (commentaire + ADR),
  le rapport de dogfooding ne les re-signale plus comme dette ouverte.
- **Dette assumée** : les deux parsers restent à CC > 10. Si l'un d'eux gagne une
  vraie logique métier (au-delà du parsing), l'exception devra être réévaluée.

## Liens

- [ADR-0021](0021-critic-self-challenge.md) — Critic self-challenge (calibration empirique, drift)
- `tools/calibration.py` — implémentation de `propose_thresholds()`
- `tools/AI_CONTEXT.md` — invariant de synchro des seuils reject/review
- `C:\Users\barat\.claude\CLAUDE.md` § « Taille des fonctions et complexité cyclomatique » (exception parsers)
