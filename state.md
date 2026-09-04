### DECISIONS
- Audit limité aux blockers P0/P1 des invariants ADR-0009 et au checkout feat/distribution-lifecycle-v1 | préserver les trois modifications utilisateur existantes | ne pas corriger pendant une revue | active

### UNCERTAINTIES
- Tests fonctionnels lancés avec escalade car le répertoire temporaire sandbox était inaccessible | le résultat ciblé est vert mais l'environnement sandbox initial ne permettait pas le runner | relancer dans un environnement temporaire accessible si nécessaire | P2

### VERIFIED FINDINGS
- `uninstall --purge` peut supprimer un fichier géré édité par l'utilisateur : `plan_component_removal` choisit REMOVE dès que `purge` est vrai malgré un digest modifié | `ainative/lifecycle/planner.py:302-318` | lecture directe | confirmed
- `uninstall --purge` récursive supprime tout fichier ajouté par l'utilisateur sous `.ai-native/lifecycle` | `ainative/lifecycle/uninstaller.py:84-100` | lecture directe | confirmed
- Un journal falsifié peut faire écrire `repair` hors du projet via un identifiant contenant `..` | `ainative/lifecycle/transaction.py:115-121,419-422`; récupération appelée par `ainative/lifecycle/recovery.py:272-274` | lecture directe | confirmed
