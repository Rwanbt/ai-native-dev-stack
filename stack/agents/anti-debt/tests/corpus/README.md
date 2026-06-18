# Corpus de tests — Anti-Dette Agent

Ce corpus contient **5 repos miniatures** avec dette technique **connue et annotée**.
Chaque fixture a un fichier `EXPECTED_FINDINGS.json` qui liste la dette qu'un agent
parfait devrait détecter (au moins au niveau de la catégorie + subcategory).

But : mesurer **precision/recall** de l'agent sur des cas connus.

## Repos du corpus

| # | Fixture | Langue | Dette attendue |
|---|---------|--------|----------------|
| 1 | `fixture1-py-messy` | Python | secrets + duplication + tests manquants |
| 2 | `fixture2-rust-complex` | Rust | fonction trop complexe |
| 3 | `fixture3-js-circular` | TypeScript | dépendance circulaire |
| 4 | `fixture4-py-secure` | Python | dépendance vulnérable (mock CVE) |
| 5 | `fixture5-clean-baseline` | Python | aucun finding (baseline négatif) |

## Métriques cibles V1

- **Precision ≥ 80%** : peu de faux positifs
- **Recall ≥ 70%** : on rate certaines dettes sémantiques, OK pour V1
- **Critic rejection rate ≤ 10%** : on ne passe pas trop de bruit

## Notes importantes

1. **Ground truth partielle** : `EXPECTED_FINDINGS.json` liste les findings **qu'un scanner déterministe devrait détecter**. Les findings LLM-inferred (architecture, sémantique) ne sont pas ground-truthés en V1.

2. **Mock CVEs** : les fixtures 1 et 4 utilisent des patterns connus pour déclencher les scanners (ex: `sk_live_...` pour trufflehog, `requests==2.18.0` pour pip-audit). Les vraies détections dépendent de la base de vulnérabilités locale.

3. **Pas de faux positifs artificiels** : chaque fixture a une dette réelle. Le test baseline (fixture5) doit retourner 0 findings de criticité high+.

## Maintenance

Quand le format des outils évolue (ruff, clippy, etc.), les `EXPECTED_FINDINGS.json`
peuvent nécessiter un recalibrage. C'est un travail manuel mais explicite.
