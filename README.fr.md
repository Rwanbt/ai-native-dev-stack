<div align="center">

<img src="ai_native_dev_stack.png" alt="Bannière AI Native Dev Stack">

[English](README.md) · Français

# AI Native Dev Stack

> **Ingénierie de contexte cross-agent, connaissance projet persistante et vérification déterministe pour les agents de code IA.**

Aidez vos agents à comprendre le codebase, conserver la connaissance d'ingénierie entre les sessions, suivre une méthode partagée et prouver le travail réalisé avant que le projet ne l'accepte.

[![CI](https://github.com/Rwanbt/ai-native-dev-stack/actions/workflows/ci.yml/badge.svg)](https://github.com/Rwanbt/ai-native-dev-stack/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](pyproject.toml)

**Intégrations :** OpenCode · Claude Code · Codex · Cursor · Gemini · MiniMax / Mavis

> Les capacités varient selon le harnais ; la méthode d'ingénierie canonique et le contrat Vault restent partagés.

</div>

---

## Démarrage rapide

Installez la stack côté projet :

```bash
pip install git+https://github.com/Rwanbt/ai-native-dev-stack.git

cd votre-projet
ainative init --profile standard
ainative status
```

Besoin de Work Contracts gouvernés et de convergence déterministe ?

```bash
ainative init --profile verified
```

| Profil | Recommandé pour | Ajoute |
|---|---|---|
| **Standard** | apprentissage, développement personnel, travail assisté par IA courant | contexte, outillage mémoire, skills, outillage AI-docs, méthode d'ingénierie |
| **Verified** | production, équipes, code critique, agents autonomes | Standard + Work Contracts, evidence, vérification déterministe, convergence |

**Verified étend Standard. Standard ne dépend jamais de Verified.** Le changement de profil est non destructif avec `ainative profile switch`.

> `ainative init` possède l'**installation projet**. L'intégration machine globale des harnais est une surface séparée et réversible ; voir [Installation projet vs. machine](#installation-projet-vs-machine).

Pas encore d'installation via `pip` ? Depuis un clone de ce repository, les scripts bootstrap délèguent au même lifecycle :

```bash
# Linux / macOS / Git Bash
bash install.sh --profile standard

# Windows PowerShell
pwsh -NoProfile -File install.ps1 -Profile standard

# Tout OS avec Python 3.11+
python install.py --profile standard
```

---

## Pourquoi AI Native ?

Les agents de code sont puissants, mais perdent régulièrement les mêmes informations : architecture, contraintes cachées, décisions précédentes, patterns de défaillance, état du projet et définition réelle de « terminé ».

AI Native Dev Stack n'est **pas un nouvel agent de code**. C'est la couche d'ingénierie autour des agents que vous utilisez déjà.

Elle fournit à plusieurs harnais IA la même méthode projet, un contexte structuré, une connaissance persistante et — avec le profil Verified — un gate déterministe entre :

> **« l'agent dit que le travail est terminé »**  
> et  
> **« le projet possède assez de preuves pour accepter ce travail comme terminé ».**

---

## Quatre piliers

Il s'agit d'un **modèle de présentation**, pas de quatre nouvelles autorités architecturales. L'ownership canonique reste dans les fichiers et contrats documentés par le repository.

| Pilier | Problème résolu | Mécanismes principaux |
|---|---|---|
| **UNDERSTAND** | Éviter de redécouvrir le codebase à chaque session | `AI_CONTEXT.md`, `AI_SUMMARY.md` généré, Context Assembler, Graphify |
| **REMEMBER** | Conserver décisions et état projet entre les sessions | Vault Obsidian, ADR, notes de session, known failure patterns |
| **WORK** | Donner à chaque agent la même méthode d'ingénierie | `AGENTS.md` canonique, skills, hooks, lifecycle, adaptateurs |
| **VERIFY** | Séparer travail déclaré et travail accepté | Work Contracts, verification runner, evidence, provenance, convergence |

### UNDERSTAND — contexte structuré du codebase

Un module est un répertoire contenant `AI_CONTEXT.md`. Ce contexte écrit à la main capture les informations que le code source seul ne communique pas toujours correctement : objectif, contraintes, modèle de threading, modes de défaillance dangereux, fichiers sensibles et ADR pertinents.

`AI_SUMMARY.md` est généré depuis les sources afin d'exposer la surface publique courante et les signaux de taille. Le Context Assembler combine contexte module, summaries, règles, ADR, failure patterns et informations de dépendances en un briefing ciblé.

[Graphify](https://github.com/safishamsi/graphify) complète ce contexte par un graphe de dépendances AST pour les requêtes structurelles, explications et chemins.

> Le scanner de modules actuel traite volontairement les sources comme des siblings directs de `AI_CONTEXT.md`. Un sous-répertoire qui nécessite son propre contexte doit devenir un sous-module explicite.

### REMEMBER — connaissance projet persistante

La connaissance projet doit rester dans des fichiers lisibles et versionnables plutôt que dans une mémoire opaque propre à un assistant.

AI Native utilise un contrat de Vault Obsidian pour organiser mémoire projet, sessions, décisions, investigations, notes de travail et relations explicites. La même connaissance peut rester lisible par les humains, accessible aux agents, récupérable via Git et portable entre plusieurs harnais IA.

Voir [Couche de connaissance et mémoire Obsidian](#couche-de-connaissance-et-mémoire-obsidian).

### WORK — une méthode, plusieurs agents

[`AGENTS.md`](AGENTS.md) est la **méthode d'ingénierie canonique unique**. Les fichiers propres aux outils sont des adaptateurs : ils référencent ou synchronisent la méthode canonique au lieu de la redéfinir indépendamment.

Les skills projet sont installés dans :

```text
.claude/skills/   # skills projet Claude Code
.agents/skills/   # convention partagée Codex / OpenCode / Cursor
```

L'intégration machine globale peut ensuite relier la méthode, les hooks, les skills, les blocs de gouvernance Vault et les adaptateurs aux clients IA détectés sans transformer leurs configurations en nouvelles sources de vérité.

Le skill first-party `verify-ai-docs` audite la stack de documentation IA et produit une scorecard OPERATIONAL/DEGRADED/BROKEN. Utilisez `/verify-ai-docs` lorsque votre harnais expose les skills installés sous forme de commandes slash.

Modèle complet de portabilité : [PORTABILITY.md](PORTABILITY.md).

### VERIFY — la preuve avant la convergence

Le Verified Work Plane évalue des Work Contracts commités et des vérifications réellement exécutées. Un appelant ne peut pas provoquer la convergence en racontant simplement que le travail a réussi.

Un cas réel de qualification historique a enregistré ce refus :

```text
RUN-3  a5246e6  NOT_CONVERGED  2 gaps

crate-tests              PASS
boundary-reachability    PASS
structured-llm-contract  PASS
hostile-adaptation-e2e   FAIL
```

La condition end-to-end en échec a empêché un faux résultat vert. Le record historique est conservé dans [`docs/REVIEW-PACKET-H01.md`](docs/REVIEW-PACKET-H01.md) ; le comportement actuel et ses limites sont documentés dans [`docs/VERIFIED-WORK-PLANE.md`](docs/VERIFIED-WORK-PLANE.md).

`ainative converge` utilise des verdicts stables :

```text
0  CONVERGED
1  NOT_CONVERGED
2  INVALID
3  INTERNAL_ERROR
```

---

## Couche de connaissance et mémoire Obsidian

Le Vault Obsidian n'est pas un simple dossier de notes de session. Il constitue la **couche persistante, lisible par l'humain, de connaissance et de mémoire projet** de la stack.

La connaissance canonique reste en Markdown. API d'accès, métadonnées Git, embeddings, index sémantiques et vues de graphe générées sont des **couches d'interaction, de retrieval, de transport ou de visualisation — jamais des sources de vérité supplémentaires**.

```text
                         Agents IA
                            │
                 ┌─────────┼─────────┐
                 │                     │
          Local REST API          MCP optionnel
         (hooks fournis)          couche d'accès
                 │                     │
                 └─────────┬─────────┘
                            ▼
                      Vault Obsidian
                   Markdown canonique
                            │
          ┌─────────────────┼────────────────┐
          │                 │                 │
     Obsidian Git     Smart Connections   Graphe natif
 historique / sync     retrieval sémantique wikilinks /
    / récupération       / embeddings      métadonnées
```

### Setup Obsidian enrichi recommandé

Il faut distinguer deux besoins d'accès :

- **Transport des hooks livrés — Local REST API.** Les hooks `SessionStart` / `SessionEnd` actuels de AI Native lisent et écrivent dans le Vault ouvert via `OBSIDIAN_API_URL` et `OBSIDIAN_API_KEY`.
- **Accès interactif des agents — MCP compatible Obsidian.** Dans un workflow enrichi, MCP permet aux agents IA d'interroger et de mettre à jour la connaissance du Vault sans copier manuellement les notes dans le contexte. AI Native ne désigne actuellement aucune implémentation de serveur MCP comme canonique.

Autour de cette couche d'accès, deux plugins Obsidian recommandés renforcent le Vault :

| Couche | Rôle | Source de vérité ? |
|---|---|---|
| **Vault Markdown** | Connaissance projet canonique | **Oui** |
| **Local REST API** | Transport utilisé par les hooks mémoire fournis | Non |
| **MCP compatible Obsidian** | Accès direct / interface de retrieval optionnelle pour les agents | Non |
| **Obsidian Git** | Historique, synchronisation, diff, récupération, portabilité multi-machine | Non |
| **Smart Connections** | Retrieval sémantique basé sur embeddings quand le nom exact ou les mots-clés sont inconnus | Non |
| **Graphe natif Obsidian** | Navigation sur les wikilinks, backlinks et métadonnées explicites | Dérivé du Markdown |

Pour le workflow Obsidian AI-native complet, pensez **MCP + Obsidian Git + Smart Connections** autour d'un Vault Markdown canonique ; Local REST API reste le transport concret utilisé par les hooks livrés dans ce repository.

Smart Connections apporte la recherche sémantique ; le graphe natif d'Obsidian représente les relations explicites. Ils répondent à deux besoins différents :

```text
wikilinks / graphe     → relations explicites
Smart Connections      → similarité et retrieval sémantiques
```

Pour une mémoire projet personnelle ou professionnelle, privilégiez un **remote Git privé** pour le Vault. Ne commitez jamais de credentials ou de secrets. La confidentialité de Smart Connections dépend de la configuration d'embeddings/provider choisie.

Une organisation v4 typique :

```text
<OBSIDIAN_VAULT>/
+── INDEX.md
+── LOG.md
+── AGENTS.md
+── projects/<slug>/
+│   └── INDEX.md
+│   └── AGENTS.md
+│   └── BOARD.md
+│   └── _memory/memory.md
+│   └── decisions/
+│   └── operations/sessions/
+│   └── work/
+└── _system/
```

Chaque harnais découvre le même contrat Vault via `OBSIDIAN_VAULT`, `OBSIDIAN_PROJECT_SLUG`, le registre projet et le validateur propre au Vault. Le contrat vit dans le Vault ; les configurations de harnais ne font qu'y pointer.

Détails opérationnels : [`hooks/README.md`](hooks/README.md) et [`scripts/README.md`](scripts/README.md).

---

## Comment les briques s'assemblent

```text
                    Agents de code IA
                          │
                adaptateurs par harnais
                          │
                          ▼
                    AGENTS.md
             méthode d'ingénierie canonique
                          │
          ┌──────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
   Contexte module    Vault Obsidian    Skills / hooks
 AI_CONTEXT/SUMMARY   mémoire projet      workflow
          │               │                │
          └──────────────┼────────────────┘
                          │
                     implémentation
                          │
                          ▼
                  Verified Work Plane
                    (Verified uniquement)
                          │
                 evidence + convergence
```

Ce design garde l'ownership explicite :

- `AGENTS.md` possède la méthode d'ingénierie.
- le Markdown projet et le Markdown du Vault possèdent le contexte et la connaissance lisibles par l'humain.
- summaries, graphes, embeddings et caches sont des vues dérivées.
- le Verified Work Plane possède l'acceptation déterministe du travail déclaré quand le profil Verified est actif.

---

## Installation projet vs. machine

AI Native sépare volontairement deux surfaces d'installation.

### 1. Lifecycle projet — `ainative`

`ainative init` installe et enregistre les composants possédés côté projet, notamment :

- `AGENTS.md`
- `conventions.json`
- `tools/ai_docs/`
- `.ai-native/templates/`
- `.claude/skills/`
- `.agents/skills/`
- `tools/ai_docs/config.sh`
- l'intégration Verified lorsque le profil Verified est choisi

Le fichier généré `tools/ai_docs/config.sh` est une **donnée utilisateur** : modifiez-le pour les chemins propres à la machine ; les mises à jour du lifecycle ne l'écrasent pas.

Après installation, le template module se trouve ici :

```text
.ai-native/templates/AI_CONTEXT_template.md
```

Commandes utiles :

```bash
ainative status
ainative doctor
ainative profile switch verified
ainative update check
ainative uninstall
```

Chaque mutation suit le modèle d'ownership non destructif du lifecycle. Voir [`docs/DISTRIBUTION-LIFECYCLE.md`](docs/DISTRIBUTION-LIFECYCLE.md).

### 2. Intégration machine globale

Depuis un clone de ce repository, l'installateur machine relie la méthode partagée et les intégrations supportées aux clients détectés :

```bash
python scripts/install_agents.py
python scripts/install_agents.py --check
python scripts/install_agents.py --dry-run
```

L'installateur machine possède des cibles explicites pour Claude Code, Codex, OpenCode, Cursor, Gemini et Mavis (l'intégration MiniMax/Mavis). L'installateur utilise des blocs/liens gérés et préserve le contenu utilisateur situé hors de ces blocs.

Guide complet : [PORTABILITY.md](PORTABILITY.md).

---

## Composants principaux

| Composant | Rôle | Canonique / dérivé |
|---|---|---|
| `AGENTS.md` | règles d'ingénierie partagées | **Canonique** |
| `AI_CONTEXT.md` | intention et contraintes propres au module | **Canonique** |
| `AI_SUMMARY.md` | snapshot API/LOC généré | Dérivé |
| Context Assembler | briefing ciblé pour un fichier | Dérivé |
| Graphify | graphe de dépendances et requêtes structurelles | Dérivé |
| Vault Obsidian | connaissance projet persistante et lisible | **Canonique pour la connaissance Vault** |
| Skills & hooks | automatisation réutilisable du workflow | Opérationnel |
| Agent anti-debt | capacité optionnelle de gouvernance de dette technique | Opérationnel |
| Verified Work Plane | evidence gouvernée et convergence déterministe | **Autorité dans le profil Verified** |

Les écosystèmes de skills tiers comme gstack peuvent coexister avec AI Native, mais ne font pas partie de la méthode d'ingénierie canonique.

---

## Documentation

| Sujet | Source |
|---|---|---|
| Méthode d'ingénierie et règles qualité | [`AGENTS.md`](AGENTS.md) |
| Ownership cross-agent et portabilité | [PORTABILITY.md](PORTABILITY.md) |
| Lifecycle projet et profils | [`docs/DISTRIBUTION-LIFECYCLE.md`](docs/DISTRIBUTION-LIFECYCLE.md) |
| Verified Work Plane | [`docs/VERIFIED-WORK-PLANE.md`](docs/VERIFIED-WORK-PLANE.md) |
| Mise à jour sans écraser le travail utilisateur | [UPDATING.md](UPDATING.md) |
| Hooks et intégration Obsidian Local REST API | [`hooks/README.md`](hooks/README.md) |
| Outils de synchronisation Vault | [`scripts/README.md`](scripts/README.md) |
| Workflow de contribution | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Contribuer

Les contributions sont bienvenues pour le support de langages, les adaptateurs, les skills, les intégrations Obsidian, les outils de vérification, la documentation et la portabilité.

Avant d'ouvrir une PR, consultez [`CONTRIBUTING.md`](CONTRIBUTING.md) et le canonique [`AGENTS.md`](AGENTS.md).

---

## Licence

MIT — libre d'utilisation, d'étude, d'adaptation et de contribution.

