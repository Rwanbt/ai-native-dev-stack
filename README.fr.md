<div align="center">

<img src="ai_native_dev_stack.png" alt="banner_ai_native_dev_stack" >

[English](README.md) · Français

# AI-Native Dev Stack

> Une méthodologie complète et une boîte à outils pour rendre tout large codebase immédiatement compréhensible par les assistants IA — avec une maintenance automatique pour que le contexte ne devienne jamais obsolète.

[![CI](https://github.com/Rwanbt/ai-native-dev-stack/actions/workflows/ci.yml/badge.svg)](https://github.com/Rwanbt/ai-native-dev-stack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Works with Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-green)](https://claude.ai/code)
[![Claude Code skill](https://img.shields.io/badge/skill-verify--ai--docs-purple)](skills/verify-ai-docs/SKILL.md)

</div>

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

[graphify](https://github.com/safishamsi/graphify) construit un graphe de dépendances au niveau AST pour tout le codebase. Au lieu de grepper "où est utilisé X ?", on interroge :

```bash
graphify explain "processRequest"   # résumé en langage clair d'un nœud + voisins
graphify path "ModuleA" "ServiceB"  # plus court chemin de dépendance entre deux nœuds
graphify update .                    # ré-indexation après modifications (secondes, pas minutes)
```

Le graphe est stocké dans `graphify-out/graph.json` et `GRAPH_REPORT.md`. L'IA et le développeur peuvent l'interroger sans relire des milliers de fichiers.

### 5. Coffre-fort mémoire Obsidian (Second cerveau)

Un coffre-fort Obsidian sert de **mémoire persistante inter-sessions**.
Le contrat v4 place un dossier par projet sous `projects/<slug>/`, où
`<slug>` est un identifiant kebab-case en minuscules enregistré dans
`<coffre>/_system/schemas/projects.json` :

```
<OBSIDIAN_VAULT>/
├── INDEX.md                    ← hub de navigation central
├── LOG.md                      ← journal chronologique de sessions (append-only)
├── SCHEMA.md                   ← conventions de frontmatter et de wikilinks
├── AGENTS.md                   ← entrée agent au niveau coffre, délègue au contrat
│
├── projects/<slug>/            ← un dossier par projet enregistré
│   ├── INDEX.md                ← navigation projet
│   ├── AGENTS.md               ← entrée agent spécifique au projet
│   ├── BOARD.md                ← board de statut générée (ne pas éditer à la main)
│   ├── _memory/memory.md       ← mémoire IA des sessions (décisions, patterns)
│   ├── decisions/              ← ADR, un par fichier
│   ├── operations/sessions/    ← un fichier par session, écrit par le hook SessionEnd
│   └── work/                   ← roadmaps, initiatives, runbooks
│
├── inbox/                      ← notes non encore triées
├── archive/                    ← contenu déplacé / superseded
└── _system/                    ← infrastructure du coffre (contrat, tooling, schémas)
```

**Découverte du contrat v4 (tous les harnais) :**
1. `OBSIDIAN_VAULT` — racine du coffre (argument CLI, puis variable d'env)
2. `OBSIDIAN_PROJECT_SLUG` — slug du projet actif (doit respecter
   `[a-z0-9]+(?:-[a-z0-9]+)*`)
3. `<coffre>/_system/schemas/projects.json` — registre des projets
4. `<coffre>/_system/tooling/vault.py check` — validateur canonique

La stack découvre le coffre via le même protocole que chaque harnais
utilise ; le contrat v4 est mono-source dans le coffre, jamais copié
dans les fichiers de configuration des harnais.

**Protocole de fin de session (obligatoire, v4) :**
1. Le hook SessionEnd écrit une note immuable dans
   `projects/<slug>/operations/sessions/<session-id>.md`
2. Il appende une ligne dans `LOG.md` (un seul append, jamais de rewrite)
3. Le hook SessionStart charge `projects/<slug>/AGENTS.md`,
   `projects/<slug>/BOARD.md`, et l'`AGENTS.md` racine du coffre

La prochaine session démarrera avec le contexte complet — même des
semaines plus tard, même sur une autre machine.

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

Les skills sont des fichiers `.md` dans `<racine-agent>/skills/<nom>/SKILL.md` — versionnés avec le projet, disponibles pour chaque contributeur. L'installeur les pose dans chaque racine d'agent : `.claude/skills` pour Claude Code, `.agents/skills` pour Codex, OpenCode et Cursor.

#### gstack — Skills d'ingénierie globaux

[gstack](https://github.com/garrytan/gstack) est une collection de skills Claude Code communautaires créée par Garry Tan (Président de YC). Elle fournit des skills d'ingénierie génériques disponibles sur **tous** vos projets, indépendamment du codebase :

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
Tier 1  — Core Scripts            8/8   ✅
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
  SCORE: 68/68 | Status: OPERATIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Auto-corrige : `AI_SUMMARY.md` obsolètes, graphe graphify périmé, hook PostToolUse manquant.  
Signale : `AI_CONTEXT.md` manquants avec templates prêts à remplir.  
Installe : guide d'installation pas-à-pas pour les nouveaux contributeurs.

### 12. Instantané de métriques (`tools/ai_docs/generate_metrics.py`)

Répond à « comment sait-on que ça marche ? » avec des mesures objectives dérivées de git, écrites dans `docs/METRICS.md` :

- **Couverture** — % des répertoires source ayant un `AI_CONTEXT.md` (cible ≥ 80 %)
- **Fraîcheur** — `AI_SUMMARY.md` à jour ; dérive de `AI_CONTEXT.md` (docs périmés alors que les sources ont changé)
- **Base de connaissances** — nombre de patterns `KNOWN_FAILURE_PATTERNS.md` et d'ADR (doit croître avec le temps)
- **Zones à risque** — répertoires à fort churn sans `AI_CONTEXT.md` (où les erreurs IA sont les plus probables)
- **Tendance** — une ligne append-only par exécution, pour suivre couverture et risque dans le temps

`/verify-ai-docs` régénère cet instantané à chaque exécution.

---

## Quel profil choisir ?

```
AI Native Dev Stack
        │
        ├── Standard    contexte · mémoire · skills · hooks · adaptateurs · docs IA
        │
        └── Verified    Standard + Work Contracts · vérification · convergence
```

### Standard

Contexte, mémoire, skills et outillage AI-native. **Recommandé pour
l'apprentissage, le développement personnel et le travail assisté par IA
ordinaire** — étudiants, développeurs seuls, installation rapide.

Standard fournit le contexte, les skills et l'outillage AI-native **côté
projet**. Les intégrations machine globales et les liaisons Vault optionnelles
s'installent séparément avec l'installateur global (`scripts/install_agents.py`).

### Verified

Standard **plus** des Work Contracts gouvernés et une vérification
déterministe. **Recommandé pour la production, les équipes et les agents
autonomes** — code critique et auditabilité.

> **Standard optimise la façon dont l'IA travaille avec le projet.**
> **Verified gouverne en plus, et vérifie de façon déterministe, le travail
> déclaré.**

Verified étend Standard ; Standard ne dépend jamais de Verified. Vous pouvez
passer de l'un à l'autre à tout moment, dans les deux sens, et redescendre vers
Standard **préserve** votre historique Verified sous forme d'état dormant au
lieu de le supprimer.

### Ce que fait `ainative init` — et ce qu'il ne fait pas

`ainative init` est le cycle de vie **du projet**. Il installe des fichiers
dans le projet uniquement (`AGENTS.md`, `conventions.json`, `tools/ai_docs/`,
skills dans le projet, la région du `.gitignore`, et l'intégration Verified si
choisie) et enregistre la propriété de chacun.

L'intégration machine globale est une surface séparée : hooks globaux, liens
de skills cross-CLI, blocs de gouvernance Vault dans `~/.claude/CLAUDE.md`,
`~/.codex/AGENTS.md`, `~/.config/opencode/`, `~/.cursor/`, `~/.gemini/` et
Mavis, et le plugin OpenCode — tout cela s'installe avec
`python scripts/install_agents.py` (voir *Installer la méthode sur la machine*
ci-dessous). Garder les deux séparés, c'est ce qui rend les deux réversibles.

---

## Démarrage rapide

### Installer sur un projet existant

Une seule CLI possède l'installation, le choix de profil, la mise à jour et la
désinstallation — et elle **enregistre ce qu'elle écrit**, pour pouvoir le
défaire. Elle copie l'outillage, installe les skills dans **toutes** les racines
d'agent (`.claude/skills` pour Claude Code, `.agents/skills` pour Codex,
OpenCode et Cursor), pose `AGENTS.md` et `conventions.json`.

```bash
pip install git+https://github.com/Rwanbt/ai-native-dev-stack.git
cd /chemin/vers/votre-projet

ainative init                          # demande Standard ou Verified
ainative init --profile standard       # non interactif
ainative init --profile verified
```

Pas encore de `pip` ? Le bootstrap fait la même chose depuis un clone :

```bash
# Linux / macOS / Git Bash
bash /chemin/vers/ai-native-dev-stack/install.sh --profile standard

# Windows, sans Git Bash ni WSL
pwsh -NoProfile -File C:\chemin\vers\ai-native-dev-stack\install.ps1 -Profile standard

# N'importe quel OS, directement
python /chemin/vers/ai-native-dev-stack/install.py --profile standard
```

Options utiles :

```bash
ainative init --profile standard --dry-run   # montre le plan, n'écrit rien
ainative status                              # ce qui est installé, et sa santé
ainative profile switch verified             # réversible dans les deux sens
ainative update check                        # détection auto, application jamais
ainative uninstall                           # retire le stack, garde votre travail

python install.py --with-gstack      # installe gstack (code tiers, opt-in)
python install.py --gstack-ref SHA   # épingle gstack à un commit précis
```

gstack n'est **pas** installé par défaut : c'est du code tiers exécuté par
votre agent. Quand vous l'installez, le commit réellement obtenu est
enregistré dans `.stack-lock.json` pour que l'installation soit reproductible.

Chaque fichier géré porte le SHA-256 qu'il avait au moment où le stack l'a
écrit. Une mise à jour n'écrase donc jamais votre modification, et une
désinstallation ne la supprime jamais. Toute mutation est transactionnelle
(sauvegarde → application → vérification → écriture de l'état **en dernier**) :
une interruption laisse l'ancien état valide ou le nouveau, jamais un projet à
moitié installé. Voir
**[docs/DISTRIBUTION-LIFECYCLE.md](docs/DISTRIBUTION-LIFECYCLE.md)** et
[ADR-0009](docs/adr/0009-distribution-profiles-and-lifecycle-ownership.md).

Déjà installé à l'ancienne, avant l'existence du lifecycle ? Rien à migrer à la
main : `ainative init` détecte les fichiers présents et les adopte sans écraser
ce que vous avez modifié.

Ensuite :

1. Référencer `AGENTS.md` depuis la config globale de votre agent — une ligne,
   jamais une copie (`@/chemin/absolu/AGENTS.md`).
2. Éditer `tools/ai_docs/config.sh` (coffre Obsidian, binaire graphify) — ce
   fichier vous appartient, l'installeur ne l'écrase jamais.
3. Enregistrer le hook PostToolUse — voir `.ai-native/templates/settings_hook_example.json`.
4. Écrire un `AI_CONTEXT.md` par module — voir `.ai-native/templates/AI_CONTEXT_template.md`.
5. Vérifier : `ainative status`, puis `/verify-ai-docs`.

### Installer la méthode sur la machine (une fois)

Installe règles, skills et agents dans **chaque CLI IA détecté** — Claude Code,
Codex, OpenCode, Cursor, MiniMax/Mavis — sous forme de **liens** et non de
copies, pour qu'un `git pull` mette tout à jour d'un coup.

```bash
bash scripts/setup-agents.sh                    # Linux / macOS / Git Bash
pwsh -NoProfile -File scripts/setup-agents.ps1  # Windows
python scripts/install_agents.py                # n'importe quel OS

python scripts/install_agents.py --check        # vérifier une installation
python scripts/install_agents.py --dry-run      # prévisualiser
```

Idempotent : une seconde exécution affiche `0 change(s)`. L'installeur ne
remplace jamais un fichier qu'il ne gère pas — il le signale `KEEP`. Sous
Windows, les liens de dossier basculent en jonctions si la création de lien
symbolique est refusée, donc aucun shell élevé n'est nécessaire.

### Vérifier que tout est cohérent

```bash
python scripts/validate_conventions.py   # AGENTS.md == conventions.json
python scripts/measure_scope.py          # les tailles annoncées sont à jour
python scripts/install_agents.py --check # les liens sont en place
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
| `docs/METRICS.md` | `generate_metrics.py` (lancé par `/verify-ai-docs`) |
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
<OBSIDIAN_VAULT>/
├── INDEX.md                  ← hub de navigation central
├── LOG.md                    ← journal chronologique de sessions (append-only)
├── SCHEMA.md                 ← conventions de frontmatter et wikilinks
│
├── projects/<slug>/          ← un dossier par projet enregistré
│   ├── INDEX.md / AGENTS.md / BOARD.md
│   ├── _memory/memory.md     ← mémoire IA des sessions (décisions, patterns)
│   ├── decisions/            ← ADRs, un par fichier
│   ├── operations/sessions/  ← une note de session par hook SessionEnd
│   └── work/                 ← initiatives, tâches, runbooks
│
├── inbox/                    ← notes non triées
├── archive/                  ← contenu déplacé/supersédé
└── _system/                  ← infrastructure du coffre (contrat, tooling, schémas)
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

Le protocole obligatoire est défini une seule fois, dans la section v4 du
coffre ci-dessus : le hook SessionEnd écrit une note de session immuable sous
`projects/<slug>/operations/sessions/` et append une seule ligne dans `LOG.md`
(append-only, jamais de réécriture) ; le hook SessionStart recharge
`projects/<slug>/AGENTS.md`, `BOARD.md` et l'`AGENTS.md` du coffre. Terminez
par `/verify-ai-docs` pour confirmer que tout est en sync.

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

## Intégration vault v4

La stack cible le contrat v4 du coffre sans le recopier : chaque
harnais (Claude Code, Codex, OpenCode, Cursor, Gemini, Mavis) découvre
le même coffre, valide de la même façon, et refuse d'écrire dans un
coffre qui ne satisfait pas le contrat.

| Concept | Prise en charge par la stack |
|---|---|
| Découverte du coffre | Argument `--vault`, puis `$OBSIDIAN_VAULT`. Jamais codé en dur. |
| Slug du projet | Argument `--project-slug`, puis `$OBSIDIAN_PROJECT_SLUG`, puis validé contre la grammaire v4 `[a-z0-9]+(?:-[a-z0-9]+)*`. |
| Détection v4 | Le protocole vérifie `_system/schemas/projects.json`, `_system/tooling/vault.py` et l'`AGENTS.md` racine. |
| Validation | La stack appelle `<coffre>/_system/tooling/vault.py check` (avec fallback `lint`) — elle ne ré-implémente pas le schéma. |
| Verrou de maintenance | Un sentinel `.git/maintenance.lock` arrête le sync. Ne le supprimer que lorsque l'orchestrateur a terminé. |
| Bloc par harnais | `scripts/install_agents.py` écrit un bloc « Vault governance » pour Claude (`~/.claude/CLAUDE.md`), Codex, OpenCode, Cursor (`~/.cursor/rules/ai-native-dev-stack.mdc`), Gemini (`~/.gemini/GEMINI.md`) et Mavis. |
| Boards | Le hook SessionEnd n'écrit jamais dans `BOARD.md` — les boards sont des vues générées ; les cartes canoniques portent le statut. |
| Sync | `scripts/vault_sync.py` exécute le validateur v4 avant le staging, préserve le scan de secrets, le single-writer, la détection de divergence et la vérification du SHA distant. |
| Check / rollback | `python scripts/install_agents.py --check --vault <coffre> --project-slug <slug>` rapporte l'état des blocs ; `python scripts/vault_sync.py --no-validator-check` est la *seule* opt-in legacy. |

### Installer, vérifier, rollback, désinstaller

```bash
# Installer : méthode + bloc « Vault governance » dans chaque harnais supporté
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug>

# Vérifier : 0 changement, 0 issue sur une installation propre
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --check

# Rollback : retirer le bloc « Vault governance » de chaque harnais.
# Le bloc de méthode d'ingénierie partagé est conservé.
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --no-vault-block

# Redémarrer chaque client IA pour qu'il recharge les règles globales.
```

### Ce que le contrat v4 n'est PAS

La stack ne fait pas :

- Coder en dur un chemin de coffre. Il n'y a aucune constante
  `D:\Documents\...` ; l'utilisateur fournit toujours le coffre, et
  un coffre non configuré est une erreur claire, pas un défaut.
- Recopier le contrat v4. Chaque bloc est un pointeur vers
  l'`AGENTS.md` du coffre ; le texte du contrat vit en un seul endroit.
- Écrire dans le coffre pendant une installation normale.
  L'installateur écrit dans les répertoires harnais au niveau utilisateur
  (`~/.claude/`, `~/.codex/`, `~/.config/opencode/`, `~/.mavis/...`) ;
  le coffre est en lecture seule du point de vue de la stack.

### Écriture locale, commit, push, publication — quatre actions distinctes

La stack ne les confond jamais. Un « push » est toujours une étape
séparée d'un « write » ou d'un « commit », et seul `scripts/vault_sync.py`
fait les deux derniers. Les hooks et les installateurs n'écrivent que
localement ; le sync est l'unique chemin vers le distant, et il
applique le contrat v4 sur le chemin.
