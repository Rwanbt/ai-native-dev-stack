<img src="ai_native_dev_stack.png" alt="banner_ai_native_dev_stack" >

[English](README.md) · Français

# AI-Native Dev Stack

> Une méthodologie complète et une boîte à outils pour rendre tout large codebase immédiatement compréhensible par les assistants IA — avec une maintenance automatique pour que le contexte ne devienne jamais obsolète.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Works with Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-green)](https://claude.ai/code)
[![Claude Code skill](https://img.shields.io/badge/skill-verify--ai--docs-purple)](skills/verify-ai-docs/SKILL.md)

---

## Le problème

Les grands codebases (60k+ lignes, multi-langage, multi-thread) saturent les fenêtres de contexte des IA. Sans structure, chaque session repart de zéro : l'IA hallucine l'architecture, ignore les contraintes temps-réel et propose des solutions qui cassent le modèle de threading.

Les palliatifs habituels (coller des fichiers dans le contexte, écrire de longs prompts) ne scalent pas. Ils sont manuels, ils deviennent obsolètes, et ils consomment des tokens sur du bruit plutôt que sur du signal.

## La solution

Un **stack d'optimisation IA auto-maintenu** — un ensemble de documents structurés, scripts et hooks qui garde l'IA perpétuellement orientée sans intervention humaine :

```
Fichiers de contexte IA (par module)   ←  mis à jour à chaque édition de fichier
Graphe de dépendances (graphify)       ←  réindexé à la demande
Règles domaine (standalone)            ←  fichier unique injecté pour le code critique
Coffre-fort mémoire (Obsidian)         ←  second cerveau persistant inter-sessions
Mémoire Claude Code                    ←  résumés de session auto-générés
Écosystème de skills                   ←  commandes de vérification domaine-spécifiques
Hook PostToolUse                       ←  garde tout en sync automatiquement
```

Une seule commande vérifie la santé du stack entier : `/verify-ai-docs`

---

## Composants du stack

### 1. Contexte IA par module (`AI_CONTEXT.md`)

Chaque module source reçoit un `AI_CONTEXT.md` écrit à la main qui capture ce qu'aucun README ne documente : **modèle de threading, patterns interdits, contraintes non-évidentes, patterns d'appel courants**.

```
src/modules/auth/
├── AI_CONTEXT.md      ← manuel : purpose, thread model, contraintes
├── AI_SUMMARY.md      ← auto-généré : types publics, fonctions, table LOC
├── AuthService.ts
├── TokenManager.ts
└── ...
```

**`AI_CONTEXT.md` couvre :**
- But du module (2-3 phrases)
- Table du modèle de threading (quelle fonction s'exécute sur quel thread)
- Contraintes (ce qui est autorisé/interdit)
- **Modes de défaillance courants** — les 3-5 bugs les plus dangereux lors d'une mauvaise utilisation
- **Fichiers chauds** — les 2-4 fichiers avec les invariants les plus dangereux ou le plus fort taux de changement
- Patterns d'usage courants avec exemples de code
- Références croisées vers les ADRs et modules liés

**`AI_SUMMARY.md` est auto-généré** depuis les headers sources à chaque édition via un hook PostToolUse. Il reflète toujours l'API publique courante : types, fonctions, comptages LOC avec alertes de taille.

### 2. Règles domaine (`docs/REALTIME_RULES.md` ou équivalent)

Un document standalone couvrant toutes les contraintes pour le code critique : thread temps-réel, sécurité, performance, protocoles réseau, etc. Injecté comme contexte quand on travaille sur du code adjacent à ces contraintes.

Sections types :
- Diagramme du modèle de threading
- Contraintes absolues du callback (zéro alloc, zéro blocage, zéro exception)
- Patterns de transfert de données lock-free
- Zones gelées (fonctions jamais refactorisées sans revue)
- Règles DSP / règles domaine spécifiques

### 3. Maintenance automatique (hook PostToolUse)

Un hook Claude Code `PostToolUse` se déclenche après chaque `Edit` ou `Write` sur un fichier source. Il détecte quel module a été modifié et régénère le `AI_SUMMARY.md` de ce module en moins d'une seconde.

```
Édition de SessionManager.cpp
    → hook se déclenche → update_on_edit.py → generate_ai_summary.py
    → AI_SUMMARY.md mis à jour avec les nouveaux types/fonctions/LOC
```

Zéro étape manuelle. Le contexte IA est toujours à jour.

### 4. Graphe de dépendances (graphify)

[graphify](https://github.com/graphify/graphify) construit un graphe de dépendances au niveau AST pour tout le codebase. Au lieu de grepper "où est utilisé X ?", on interroge :

```bash
graphify query "qui appelle processRequest"
graphify path "ModuleA" "ServiceB"
graphify update .    # ré-indexation après modifications (secondes, pas minutes)
```

Le graphe est stocké dans `graphify-out/graph.json` et `GRAPH_REPORT.md`. L'IA et le développeur peuvent l'interroger sans relire des milliers de fichiers.

### 5. Coffre-fort mémoire Obsidian (Second cerveau)

Un coffre-fort Obsidian sert de **mémoire persistante inter-sessions**. Le coffre a un dossier dédié par projet :

```
Obsidian/MonCoffre/
├── INDEX.md                  ← hub de navigation central
├── LOG.md                    ← journal chronologique de sessions (append-only)
├── SCHEMA.md                 ← conventions de frontmatter et de wikilinks
│
├── ProjetA/                  ← un dossier par projet
│   ├── _memory/
│   │   └── memory.md         ← mémoire IA des sessions (décisions, patterns)
│   ├── decisions-log.md      ← décisions notables avec [[wikilinks]] ADR
│   └── architecture/
│       └── module-notes.md
│
├── ProjetB/                  ← autre projet
│   └── _memory/memory.md
│
└── _global/                  ← notes transversales à tous les projets
    ├── professional-code-standards.md
    └── handoff/
```

**Protocole de fin de session (obligatoire) :**
1. Mettre à jour `ProjetA/_memory/memory.md` avec les faits saillants de la session
2. Appender une entrée dans `LOG.md` : `## YYYY-MM-DD — [Projet] — résumé 3-5 bullets`

La prochaine session démarrera avec le contexte complet — même des semaines plus tard, même sur une autre machine.

**Conventions wikilinks :**
- Chaque note lie vers les notes connexes via `[[wikilinks]]`
- Les décisions architecturales lient vers leur ADR : `[[ADR-0004 Extract Service Pattern]]`
- Le champ `related:` du frontmatter est toujours renseigné

### 6. Mémoire Claude Code

Claude Code persiste une mémoire inter-sessions dans `~/.claude/projects/<clé-projet>/memory/`. Quatre types de mémoire :

| Type | Contenu | Quand enregistrer |
|---|---|---|
| `user` | Profil du développeur, expertise, préférences | En apprenant sur le développeur |
| `feedback` | Corrections et confirmations d'approche | Quand le dev corrige ou valide un pattern |
| `project` | Objectifs, deadlines, travaux en cours | En apprenant l'état du projet |
| `reference` | Pointeurs vers systèmes externes (Linear, Grafana, Notion) | En découvrant des ressources externes |

`MEMORY.md` est un index (≤ 200 lignes) pointant vers des fichiers de topic individuels. Il est chargé automatiquement au démarrage de session.

### 7. ADRs — Décisions d'architecture (`docs/adr/`)

Toute décision architecturale non triviale reçoit un ADR dans `docs/adr/NNNN-titre.md` :

```markdown
# ADR-0004 : Pattern Host struct — extraction de services
**Date** : 2026-05-07 | **Statut** : Accepté

## Contexte
Le fichier principal (18 000 LOC) concentre trop de responsabilités.

## Décision
Extraire chaque domaine dans un service dédié avec un Host struct
passé par paramètre (pas de singleton, injection explicite).

## Conséquences
Services testables en isolation. Zéro état global. Ownership traçable.
```

Le code référence les ADRs directement : `// See ADR-0004: Host struct pattern`. Cela connecte le *pourquoi* au *où*.

### 8. Catalogue des défaillances connues (`docs/KNOWN_FAILURE_PATTERNS.md`)

Un catalogue écrit à la main, append-only, des bugs les plus dangereux du codebase — organisé par catégorie (threading, FFI, sérialisation, UI, etc.). Chaque entrée : symptôme, cause racine, méthode de détection, prévention.

C'est la **mémoire institutionnelle de la douleur** : chaque post-mortem qui identifie un problème systémique y ajoute une entrée. Les nouveaux contributeurs le lisent avant de toucher des zones sensibles.

```markdown
## 1. Violations thread temps-réel

### 1.1 Allocation mémoire dans le callback audio
**Symptôme** : Craquements aléatoires sous charge.
**Cause** : std::vector::push_back (resize) à l'intérieur du callback.
**Détection** : Wrapper malloc avec _CrtSetAllocHook en builds debug.
**Prévention** : Pré-allouer tous les buffers au démarrage.
```

### 9. Assembleur de contexte (`tools/ai_docs/assemble_context.py`)

L'**Assembleur de contexte** génère un document de briefing unique et focalisé pour n'importe quel fichier source :

```bash
python tools/ai_docs/assemble_context.py src/services/payment/PaymentGateway.cpp
# La sortie inclut :
# - AI_CONTEXT.md du module (purpose, thread model, contraintes, modes de défaillance)
# - AI_SUMMARY.md (snapshot API publique)
# - docs/REALTIME_RULES.md (si contraintes RT détectées)
# - ADRs référencés (depuis la section ## See also)
# - KNOWN_FAILURE_PATTERNS.md (si existant)
# - Chemin de dépendance graphify (si binaire disponible)
# - Extrait MEMORY.md Claude Code (50 premières lignes)
```

Remplace le besoin de collecter manuellement le contexte avant de travailler sur un module. L'IA reçoit toutes les informations pertinentes en un seul document assemblé.

### 10. Écosystème de skills

Les skills Claude Code étendent l'assistant avec des commandes domaine-spécifiques et conscientes du projet.

#### Skills project-spécifiques (ce stack)

| Skill | But |
|---|---|
| `/verify-ai-docs` | Bilan de santé complet du stack (10 tiers) |
| `/verify-standards` | Scorecard qualité — CI, docs, conventions, métriques |

Les skills sont des fichiers `.md` dans `.claude/skills/<nom>/SKILL.md` — versionnés avec le projet, disponibles pour chaque contributeur.

#### gstack — Skills d'ingénierie globaux

[gstack](https://github.com/garrytan/gstack) est une collection de skills Claude Code communautaires créée par Gary Tan (Président de YC). Elle fournit des skills d'ingénierie génériques disponibles sur **tous** vos projets, indépendamment du codebase :

| Skill | But |
|---|---|
| `/investigate` | Debug root-cause guidé en 4 phases |
| `/review` | Revue de code pré-landing avec auto-fixes |
| `/health` | Dashboard santé rapide (tests, lint, build) |
| `/plan-eng-review` | Revue d'architecture avant implémentation |
| `/plan-ceo-review` | Revue stratégique de scope et d'ambition |
| `/office-hours` | Brainstorming produit style YC Office Hours |
| `/qa` | QA systématique avec navigateur headless + fixes |
| `/ship` | Release engineering — tests, PR, push |
| `/ci-heal` | Répare automatiquement les CI GitHub Actions cassées |
| `/codex` | Second avis via Codex CLI (mode adversarial) |
| `/context-save` / `/context-restore` | Checkpoint de progression inter-sessions |
| `/document-release` | Mise à jour de la doc après ship |

**Intégration avec ce stack :** gstack et les skills project-spécifiques sont **complémentaires**. gstack gère le workflow d'ingénierie général (`/review`, `/ship`, `/qa`) ; les skills project-spécifiques gèrent la qualité interne du codebase (`/verify-ai-docs`, `/verify-standards`). Les deux coexistent dans `~/.claude/skills/`.

Installation : voir la documentation de gstack sur GitHub.

### 11. Le skill `/verify-ai-docs`

Un bilan de santé en 10 tiers qui vérifie, auto-corrige et rapporte l'état de tout le stack :

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AI OPTIMIZATION STACK — HEALTH SCORECARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tier 1  — Core Scripts            6/6   ✅
Tier 2  — AI Documentation       16/16  ✅  ← inclut vérification couverture
Tier 3  — AI_SUMMARY Freshness   14/14  ✅
Tier 4  — Automation Chain        3/3   ✅
Tier 5  — graphify Graph          3/3   ✅
Tier 6  — Obsidian Memory Vault   5/5   ✅
Tier 7  — Claude Code Memory      3/3   ✅
Tier 8  — Project Quality Gates   6/6   ✅  ← inclut KFP
Tier 9  — Skills Ecosystem        7/7   ✅
Tier 10 — Cognitive Contract      3/3   ✅  ← modes défaillance · KFP · assembleur
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SCORE: 66/66 | Status: OPERATIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Auto-corrige : `AI_SUMMARY.md` obsolètes, graphe graphify périmé, hook PostToolUse manquant.  
Signale : `AI_CONTEXT.md` manquants avec templates prêts à remplir.  
Installe : guide d'installation pas-à-pas pour les nouveaux contributeurs.

---

## Démarrage rapide

### Pour un projet existant

```bash
# 1. Copier les scripts dans votre projet
cp -r tools/ai_docs/ votre-projet/tools/
cp -r skills/ votre-projet/.claude/

# 2. Configurer les chemins machine-spécifiques
cp tools/ai_docs/config.sh.example votre-projet/tools/ai_docs/config.sh
# Éditer config.sh : renseigner OBSIDIAN_VAULT, GRAPHIFY_BIN, CLAUDE_MEMORY_KEY

# 3. Enregistrer le hook PostToolUse dans .claude/settings.json
# (voir templates/settings_hook_example.json)

# 4. Écrire AI_CONTEXT.md pour chaque module majeur
# (voir templates/AI_CONTEXT_template.md)

# 5. Générer tous les AI_SUMMARY.md
python tools/ai_docs/generate_all.py

# 6. Vérifier le stack complet
# Dans Claude Code : /verify-ai-docs
```

### Pour une nouvelle machine / un nouveau contributeur

```bash
# 1. Cloner le projet (les scripts sont déjà commités)
git clone <repo-du-projet>

# 2. Détecter Python
bash tools/ai_docs/find_python.sh

# 3. Copier et éditer la config machine
cp tools/ai_docs/config.sh.example tools/ai_docs/config.sh
# Renseigner le chemin du coffre Obsidian, Python, binaire graphify

# 4. Enregistrer le hook (une fois)
# Ajouter dans .claude/settings.json → hooks.PostToolUse → Edit|Write :
# { "type": "command", "command": "bash /chemin-absolu/tools/ai_docs/run_hook.sh" }

# 5. Générer les summaries
python tools/ai_docs/generate_all.py

# 6. Vérifier → /verify-ai-docs doit afficher OPERATIONAL
```

---

## Standards de qualité — optimisation IA et lisibilité humaine

Cette méthodologie optimise simultanément pour **deux audiences** : l'IA (fenêtre de contexte, signal/bruit, précision) et les humains (maintenabilité, revue de code, onboarding). Les mêmes règles servent les deux.

### Taille des fichiers

| Seuil | Action |
|---|---|
| ≤ 500 LOC | Zone verte — fichier sain |
| > 500 LOC (nouveau fichier) | Signaler, proposer décomposition |
| > 800 LOC (fichier modifié) | Proposer extraction des responsabilités secondaires |
| > 1 500 LOC | **Refactoring obligatoire avant tout ajout** |

**Pourquoi ça aide l'IA :** Un fichier de 300 LOC rentre dans le contexte d'un seul appel. Un fichier de 2 000 LOC nécessite des allers-retours ou du tronquage — avec risque d'hallucination sur les parties non vues.

**Pourquoi ça aide les humains :** Règle SonarQube industrielle. Un fichier qu'on ne peut pas lire en entier en 5 minutes ne peut pas être relu correctement.

### Taille des fonctions et complexité

| Métrique | Cible | Alerte | Bloquant |
|---|---|---|---|
| LOC par fonction | ≤ 50 | > 100 | > 200 |
| Complexité cyclomatique | ≤ 10 | > 15 | > 25 |
| Profondeur d'imbrication | ≤ 3 | 4 | > 4 |

**Pourquoi ça aide l'IA :** Une fonction de 50 LOC peut être comprise dans un seul bloc de contexte. Une fonction de 500 LOC génère de l'incertitude : l'IA ne peut pas garder en tête toutes les branches en même temps.

### Politique de commentaires — WHY, jamais WHAT

```cpp
// ❌ Décrit CE QUE fait le code (le code se lit déjà)
// Iterate over all tracks and mute them
for (auto& track : tracks) { track.muted = true; }

// ✅ Documente POURQUOI cette contrainte existe
// Must process in reverse order — forward pass causes PDC drift (ADR-0007)
for (auto it = tracks.rbegin(); it != tracks.rend(); ++it) { ... }
```

**Pourquoi ça aide l'IA :** Les commentaires WHY sont de l'information à haute densité — ils expliquent des contraintes non inférables du code. Les commentaires WHAT sont du bruit pur pour l'IA (qui peut lire le code elle-même).

### Nommage explicite

- `processAudioFrame()` > `process()` — sans ambiguïté sur le domaine
- `userEmailAddress` > `email` — sans ambiguïté sur le type et la portée
- `MAX_RETRY_COUNT` > `MAX` — sans ambiguïté sur l'usage
- Pas d'abréviations cryptiques : `idx` → `index`, `cnt` → `count`, `mgr` → `manager`

**Pourquoi ça aide l'IA :** Les noms explicites éliminent l'ambiguïté à résolution coûteuse. L'IA n'a pas à inférer ce que fait `process()` dans un contexte audio/réseau/données.

### Zéro dead code

Supprimer immédiatement, ne jamais commenter. Un bloc commenté est plus dangereux que supprimé : il pollue le contexte de l'IA avec du code qui n'est plus exécuté.

```bash
# Détection
grep -r "TODO\|FIXME\|HACK\|XXX" src/   # chaque occurrence = ticket ou suppression
```

**Pourquoi ça aide l'IA :** Chaque ligne de code mort consomme des tokens et peut induire l'IA en erreur sur ce qui est actif. Git permet de retrouver tout code supprimé via `git log -S "nom_fonction"`.

### Responsabilité unique (SRP)

Avant d'écrire dans un fichier existant, trois questions :
1. **"Ce code appartient-il vraiment ici ?"** — si non, créer le fichier approprié
2. **"Est-ce que j'ajoute une deuxième responsabilité ?"** — si oui, fichier séparé
3. **"Ce helper est-il réutilisable ailleurs ?"** — si oui, extraire en module partagé

**Pourquoi ça aide l'IA :** Un fichier = une responsabilité = un contexte clair. L'IA peut raisonner sur un module sans avoir à comprendre des préoccupations entremêlées.

### Zéro état global — singletons inclus

**Interdit** : `static T g_xxx` dans un `.cpp` (ou `lazy_static` non justifié en Rust). **Interdit aussi** : les singletons via `getInstance()` — ils sont des globals déguisés.

Préférer l'injection de dépendances explicite : paramètre, membre de classe avec owner identifiable.

**Pourquoi ça aide l'IA :** L'état global rend le raisonnement non-local impossible. L'IA ne peut pas analyser une fonction sans tracer tous les globals qu'elle peut modifier.

### Gestion des erreurs — jamais silencieuse

- **Rust** : `unwrap()` et `expect()` interdits en production sauf invariant prouvé
- **C++** : Jamais de `catch(...)` vide — toujours traiter ou re-lancer
- **TypeScript** : Jamais de `catch (e) {}` vide — logger ou propager

**Pourquoi ça aide l'IA :** Les erreurs silencieuses créent des états incohérents que l'IA diagnostiquera comme des bugs dans du code sain. Les erreurs explicites donnent à l'IA des signaux clairs.

### Taille des PRs

≤ 400 LOC modifiées par PR (ajouts + suppressions). Au-delà, le reviewer ne peut pas maintenir sa concentration — et l'IA non plus.

**Pourquoi ça aide l'IA :** Une PR de 400 LOC peut être analysée en une passe. Une PR de 4 000 LOC nécessite plusieurs passes avec perte de cohérence.

### Documentation proportionnelle à la taille du projet

| Seuil projet | Documents obligatoires |
|---|---|
| > 10 fichiers source | `CLAUDE.md` — instructions IA + conventions |
| > 3 000 LOC totaux | `ARCHITECTURE.md` — thread model, data flow, ownership |
| > 5 000 LOC | `CONTRIBUTING.md` — conventions, onboarding, checklist PR |
| Module complexe | `docs/adr/` — décisions architecturales |

**Pourquoi ça aide l'IA :** `CLAUDE.md` est chargé automatiquement dans chaque session. `ARCHITECTURE.md` évite les hallucinations sur le design global. Les ADRs expliquent les décisions contre-intuitives.

### Conventions de commit (Conventional Commits)

```
feat: add JWT token refresh mechanism
fix: prevent double-trigger in event handler
refactor: extract PaymentService from AppController
perf: pre-allocate audio buffers at startup
docs: add threading constraints to AudioModule AI_CONTEXT
```

**Pourquoi ça aide l'IA :** L'IA peut parcourir `git log` et comprendre immédiatement l'historique sans lire chaque diff. Les commits atomiques et conventionnels permettent de trouver l'introduction d'un bug avec `git bisect` en minutes.

---

## Référence des fichiers

### Auto-maintenus (ne jamais éditer manuellement)
| Fichier | Mis à jour par |
|---|---|
| `*/AI_SUMMARY.md` | Hook PostToolUse à chaque édition de fichier source |
| `graphify-out/graph.json` | `graphify update .` (manuellement ou après grands refactors) |

### Écrits à la main (stables, versionnés)
| Fichier | Contenu |
|---|---|
| `*/AI_CONTEXT.md` | Purpose, thread model, contraintes, modes de défaillance |
| `docs/REALTIME_RULES.md` | Contraintes du thread temps-réel (ou équivalent domaine) |
| `docs/KNOWN_FAILURE_PATTERNS.md` | Catalogue des bugs systémiques |
| `docs/adr/NNNN-*.md` | Décisions d'architecture |
| `CLAUDE.md` | Instructions IA au niveau projet et conventions |

### Machine-spécifiques (git-ignorés)
| Fichier | Contenu |
|---|---|
| `tools/ai_docs/config.sh` | Chemins locaux : coffre Obsidian, Python, graphify, mémoire Claude |

---

## Structure du coffre Obsidian

```
Obsidian/MonCoffre/
├── INDEX.md                  ← hub de navigation central
├── LOG.md                    ← journal chronologique de sessions
├── SCHEMA.md                 ← conventions de frontmatter et wikilinks
│
├── ProjetA/                  ← un dossier par projet
│   ├── _memory/
│   │   └── memory.md         ← mémoire IA des sessions (décisions, patterns)
│   ├── decisions-log.md      ← décisions notables avec [[wikilinks]] ADR
│   └── architecture/
│       └── notes.md
│
├── ProjetB/                  ← autre projet
│   └── _memory/memory.md
│
└── _global/                  ← notes transversales
    ├── professional-code-standards.md
    └── handoff/
```

### Template frontmatter (chaque note du coffre)

```yaml
---
project: projet-a          # identifiant du projet
type: architecture         # architecture | decision | bug | reference | roadmap | log
tags: [projet-a, services, refactor]
summary: "Une phrase décrivant cette note pour les futures sessions IA (15-25 mots)."
created: 2026-05-14
updated: 2026-05-14
related: [[INDEX]], [[ProjetA/CLAUDE]], [[ADR-0004]]
---
```

### Format d'enregistrement de session (`LOG.md`)

```markdown
## 2026-05-14 — Projet A — Extraction du service d'authentification

- Extrait `TokenValidator`, `SessionManager`, `RefreshHandler` depuis `AppController`
- −240 LOC net, AppController.ts passe de 1 850 à 1 610 LOC
- Tous les tests passent, 0 warning lint
- Pattern : Host struct injecté par paramètre — pas de singleton
- Prochain : extraire `PermissionChecker` (~180 LOC estimé)
```

---

## Protocole de fin de session

À la fin de chaque session (obligatoire) :

1. **Mettre à jour la mémoire projet** (`ProjetA/_memory/memory.md`) :
   - Ce qui a été construit/décidé
   - Patterns découverts
   - Prochaines étapes

2. **Appender dans `LOG.md`** :
   ```
   ## YYYY-MM-DD — [Projet] — Résumé (3-5 bullets)
   ```

3. **Lancer `/verify-ai-docs`** pour confirmer que tout est en sync.

La prochaine session — même des semaines plus tard, même sur une autre machine — démarrera avec le contexte complet.

---

## Adaptation à votre projet

### 1. Liste des modules
L'auto-découverte est basée sur la présence de `AI_CONTEXT.md`. Aucune liste hardcodée à maintenir — placez simplement un `AI_CONTEXT.md` dans chaque répertoire de module.

### 2. Chemins machine
Copier `tools/ai_docs/config.sh.example` vers `config.sh` et renseigner :
- `GRAPHIFY_BIN` — chemin vers le binaire graphify
- `OBSIDIAN_VAULT` — racine de votre coffre Obsidian
- `OBSIDIAN_PROJECT_DIR` — sous-dossier pour ce projet
- `CLAUDE_MEMORY_KEY` — nom du sous-dossier dans `~/.claude/projects/`

### 3. `AI_CONTEXT.md`
Écrire un fichier par module en utilisant `templates/AI_CONTEXT_template.md`. Se concentrer sur :
- Ce que fait le module (2-3 phrases)
- Quelles fonctions s'exécutent sur quel thread
- Ce qui est interdit ici
- Les 3-5 bugs les plus fréquents quand on se trompe
- Un exemple d'usage concret

### 4. `KNOWN_FAILURE_PATTERNS.md`
Créer `docs/KNOWN_FAILURE_PATTERNS.md` et l'alimenter après chaque post-mortem. Format :
```markdown
### N.N — Titre court
**Symptôme** : Ce que le développeur observe.
**Cause** : Pourquoi ça arrive.
**Détection** : Comment le détecter (tool, assert, log).
**Prévention** : Règle à suivre pour ne jamais y retomber.
```

### 5. Règles domaine
Adapter ou créer un fichier `docs/REALTIME_RULES.md` (ou `SECURITY_RULES.md`, `PROTOCOL_RULES.md`...) selon les contraintes de votre domaine. Le nom n'a pas d'importance — l'assembleur de contexte l'injecte si des mots-clés de contrainte RT sont détectés dans `AI_CONTEXT.md`.

---

## Pourquoi ça marche

| Problème | Solution |
|---|---|
| L'IA oublie l'architecture entre sessions | LOG Obsidian + mémoire Claude Code |
| L'IA propose du code interdit dans une zone critique | Règles domaine injectées comme contexte |
| L'IA ignore quel thread exécute quelle fonction | Table thread model dans `AI_CONTEXT.md` |
| L'IA suggère d'appeler une fonction depuis le mauvais module | `graphify query` expose le graphe d'appel |
| `AI_SUMMARY.md` devient obsolète après des changements | Hook PostToolUse le régénère automatiquement |
| Nouveau contributeur → contexte IA zéro | `/verify-ai-docs` imprime le guide d'installation |
| "Quels modules existent ?" → grep | Tables LOC `AI_SUMMARY.md` + graphify |
| Répétition des mêmes bugs systémiques | `KNOWN_FAILURE_PATTERNS.md` — mémoire institutionnelle |
| Fichier trop gros → hallucinations IA | Standards LOC + refactoring obligatoire à 1 500 |

---

## Licence

MIT — utilisation libre, adaptation à votre projet, contributions bienvenues.

---

## Contribuer

PRs bienvenues pour :
- Support de langages additionnels (optimisé C++/Rust/TypeScript ; templates Python/Go bienvenus)
- Alternatives à graphify pour d'autres langages
- Templates de skills supplémentaires
- Intégrations Obsidian
- Traductions du README
