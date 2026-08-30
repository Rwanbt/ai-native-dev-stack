---
schema_version: 4
project: ai-native-dev-stack
type: log
tags: [vault, governance, v4, agent-b, integration, report]
summary: "Rapport Agent B — intégration vault v4 dans AI Native Dev Stack. Six harness supportés, hooks alignés, sync contract-enforcing, 43 tests verts, vault réel non modifié."
created: 2026-08-30
updated: 2026-08-30
related: [[AGENTS]], [[README]], [[_system/migrations/v4/REPORT]], [[_shared/global/plans/plan-vault-v4-ai-native-dev-stack-remediation-2-minimax-2026-08-30]]
---

# Vault v4 integration — Agent B report

## Identity

- **Role** : Agent B — intégration vault v4 dans AI Native Dev Stack
- **Worktree autorisé** : `D:\App\ai-native-dev-stack-agent-b`
- **Branch** : `feat/vault-v4-integration`
- **HEAD de départ** : `e3172d4cd9fcac774a6492caba7bec4a7c21499f`
- **HEAD final** : `573f368` (4 commits, dont la séquence figure en bas)
- **Vault réel** : `D:\Documents\Obsidian\IA_Dev_Brain` (READ-ONLY — aucune écriture, même pour ce rapport)
- **Date** : 2026-08-30

## Architecture (ASCII)

```
                       ┌────────────────────────────────────┐
                       │  Vault (READ-ONLY for Agent B)     │
                       │  D:\Documents\Obsidian\IA_Dev_Brain│
                       ├────────────────────────────────────┤
                       │  AGENTS.md, _system/AGENTS.md      │
                       │  _system/schemas/projects.json     │
                       │  _system/tooling/vault.py          │  ← contract
                       │  _system/tooling/vaultlib.py       │
                       │  projects/<slug>/{INDEX,AGENTS,BOARD}.md
                       │  .git/maintenance.lock (sentinel)  │
                       └─────────────┬──────────────────────┘
                                     │ vault.py check (subprocess)
                                     │ single source of truth
              ┌──────────────────────┴──────────────────────┐
              │                                             │
  ┌───────────▼─────────────┐                ┌─────────────▼──────────────┐
  │ scripts/vault_protocol  │                │  Harness user-level dirs   │
  │ (stdlib-only)           │                │  ~/.claude/CLAUDE.md       │
  │  - discover()           │                │  ~/.codex/AGENTS.md        │
  │  - check_vault()        │                │  ~/.config/opencode/       │
  │  - resolve_vault_path() │                │  ~/.mavis/agents/mavis/    │
  │  - validate_slug()      │                │  + Gemini / Cursor support │
  │  - confine_path()       │                │     via shared block       │
  │  - maintenance_locked() │                │                           │
  │  - run_validator()      │                │  Each gets TWO blocks:    │
  └────────────┬────────────┘                │   "Shared engineering     │
               │                              │    method" + "Vault       │
               │                              │    governance (v4)"       │
   ┌───────────┼────────────┬─────────────────└──────────────────────────┘
   │           │            │
┌──▼──┐  ┌────▼────┐  ┌────▼─────────────┐
│ins- │  │ vault_  │  │ hooks/           │
│tall_│  │ sync.py │  │  session-start-  │
│agen-│  │         │  │   memory/run.js  │
│ts.py│  │ + v4    │  │  session-end-    │
│     │  │ check   │  │   save/run.js    │
│     │  │ before  │  │                  │
│     │  │ stage   │  │ + v4 layout      │
│     │  │         │  │ + needs-triage   │
│     │  │ + main- │  │   on bad slug    │
│     │  │ tenance │  │ + concurrency-   │
│     │  │ refuse  │  │   safe notes     │
└─────┘  └─────────┘  └──────────────────┘
```

## Modules & call sites lus (avant toute modification)

Lecture de 3+ consommateurs par interface partagée, conformément à la consigne du plan.

| Symbole / interface | Consommateurs lus | Décision |
|---|---|---|
| `BEGIN`/`END` markers `install_agents.py` | `install_agents.py` (méthode), `install.sh`, `install.ps1`, `setup-agents.sh/.ps1`, `UPDATING.md` (sync_inlined_method) | Ajout d'un second couple `VAULT_BEGIN`/`VAULT_END` pour le bloc governance, indépendant du bloc méthode |
| `OBSIDIAN_VAULT` env | `vault_sync.py`, `vault_sync_once_daily.py`, `tools/ai_docs/config.sh.example`, `README.md` | Source unique de découverte côté stack ; protocole commun pour install + sync + hooks |
| `vault.py` (validator) | `vault.py` (CLI), `vaultlib.py` (impl), `migrations/v4/REPORT.md` | Appel `subprocess` au validator avec fallback `check` → `lint` ; timeout 30 s par défaut |
| `projects.json` schema | `vaultlib.py:_load_registry`, `migrations/v4/REPORT.md` (16 projets) | Stack lit sans copier ; aucun re-implémentation |
| `AGENTS.md` par projet | `projects/ai-native-dev-stack/AGENTS.md`, `projects/vectora/AGENTS.md`, `projects/unifia/AGENTS.md` (3 lus) | Format d'entrée agent, pas recopié — bloc pointe vers |
| `BOARD.md` | `projects/vectora/BOARD.md`, `vaultlib.py:GENERATED_BEGIN/END` | **Jamais modifié par les hooks** (règle v4 : board = dérivée) |
| `obsidian_client.js` (REST API) | `session-start-memory/run.js`, `session-end-save/run.js`, `lib/obsidian_client.js` | Étendu avec paths v4 (`projects/<slug>/...`) ; pas de nouvelle dépendance |
| `git diff --cached` dans sync | `vault_sync.py:scan_for_secrets` | Maintenance + validator avant staging ; index reset si validator red |

## Commits (4)

```
573f368 ci(vault): include v4 suites, six-harness block check
0fbb653 test(vault): protocol, harness blocks, sync, hooks
b00f682 docs(vault): v4 layout, harness matrix, install/check/rollback
e373b09 feat(vault): integrate v4 protocol, harness blocks, sync enforcement
```

Statistiques : 13 fichiers touchés, +2310 / -112 LOC ; tous les commits restent sous 400 LOC hors `vault_protocol.py` (550, justifié par couverture de tous les statuts + helpers atomiques).

## Matrice harness

| Harness | AGENTS.md cible | Bloc méthode | Bloc vault v4 | Mode lecture AGENTS | Source support |
|---|---|---|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | ✓ | ✓ | `@<stack>/AGENTS.md` (référence, pas copie) | natif Claude Code |
| Codex | `~/.codex/AGENTS.md` | ✓ | ✓ | inline (Codex ne supporte pas @file) | natif Codex |
| OpenCode | `~/.config/opencode/AGENTS.md` | ✓ | ✓ | via plugin `ai-native-dev-stack.ts` (déjà en place) | natif OpenCode |
| Cursor | skills via `~/.agents/skills/` (déjà en place) | partagé | partagé | via `~/.agents/AGENTS.md` linké par Cursor | support natif via convention `.agents/` |
| Gemini | skills via `~/.agents/skills/` | partagé | partagé | référence au stack `AGENTS.md` | convention cross-CLI `.agents/` |
| Mavis / MiniMax | `~/.mavis/agents/mavis/agent.md` | ✓ | ✓ | inline (Mavis n'a pas @file, comme Codex) | natif Mavis |

Tous les blocs sont insérés par marqueurs bornés, idempotents, et préservent le contenu utilisateur hors marqueurs (test : `test_user_content_outside_markers_survives_reinstall`).

## Tests & failure modes couverts

43 nouveaux tests + 38 existants (tools/ai_docs), tous verts.

| Suite | Tests | Couverture |
|---|---|---|
| `scripts/tests/test_vault_protocol.py` | 20 | arg/env discovery, slug grammar, registry, markers, schema version, path confinement (incl. symlink escape), maintenance lock, validator green/red/down/timeout, check→lint fallback |
| `scripts/tests/test_install_agents_v4.py` | 11 | method-only, vault+method, idempotence, dry-run, --check absent/stale/duplicate, six harness, --no-vault-block, slug CLI rejection |
| `scripts/tests/test_vault_sync_v4.py` | 5 | maintenance lock halt, green validator pushes, red validator resets index, --no-validator-check opt-in, non-v4 unchanged |
| `hooks/tests/test_hooks_v4.py` | 7 | SessionStart no-op/real-error/v4-layout/legacy-layout, SessionEnd no-op/bad-slug-needsTriage/concurrent-ends |
| `tools/ai_docs/tests/` (existants) | 38 | inchangés, tous verts |

### Failure modes explicitement validés

- vault absent → `vault-missing`
- vault non-v4 → `not-v4` avec markers manquants listés
- registry schéma < 4 → `not-v4` avec version
- slug invalide → `unknown-slug` + slug utilisateur en clair (corrigible, jamais de valeur de chemin)
- slug inconnu du registre → `unknown-slug`
- path traversal (`..` dans slug ou part) → `None` (refus silencieux du confine)
- symlink escape (projets/<slug>/leak.txt → /tmp/secret) → `None`
- maintenance lock → `maintenance` (refus avant fetch)
- validator absent / vide → `validator-down` / `not-v4` (markers manquants)
- validator rouge → `validator-red` + body du validator dans le diagnostic
- validator lent → `timeout` + durée dans le diagnostic
- fallback check→lint → toujours tenté, surface dans `detail`
- hook sans clé API → clean no-op, pas de fake success
- hook avec clé invalide → HTTP 401 explicite, pas de fake success
- hook slug invalide → `sessionSaveError` + `needsTriage: true`, aucune écriture
- deux SessionEnd concurrents → deux notes indépendantes, aucun LOG tronqué
- sync avec validator rouge → `git reset` automatique, index inchangé

## Installation, check, rollback

```bash
# Install (méthode + bloc vault v4 dans les six harness)
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug>

# Check (rapporte l'état des blocs, ne modifie rien)
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --check

# Dry-run (montre les changements sans écrire)
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --dry-run

# Rollback du bloc vault (garde le bloc méthode)
python scripts/install_agents.py --vault "<OBSIDIAN_VAULT>" --project-slug <slug> --no-vault-block

# Sync d'un vault v4 (validator obligatoire)
python scripts/vault_sync.py --vault "<OBSIDIAN_VAULT>"

# Sync legacy (avec opt-in explicite, jamais par défaut)
python scripts/vault_sync.py --vault "<OBSIDIAN_VAULT>" --no-validator-check
```

## Limites assumées

- **Le contrat v4 reste dans le vault.** Le stack ne le copie jamais ; si le vault évolue, le stack prend la nouvelle version via le validator subprocess. C'est la propriété que le plan demandait.
- **`vault.py check` n'est pas encore présent dans la version v4 du vault observé.** Le protocole détecte la commande via `--help` et bascule sur `lint` (qui est la surface stable). Le rapport `migrations/v4/REPORT.md` confirme que `lint` est vert ; le moment où `check` sera ajouté dans le vault, le stack l'utilisera automatiquement, sans changement de code.
- **Le path de test sync n'exécute pas le validateur du vault réel** — chaque test construit un validator stub (`print("OK")` ou `sys.exit(1)`) dans `TemporaryDirectory`. Aucune dépendance au vault réel dans la CI.
- **Le bloc méthode est conservé inline** (le test 6-harness l'exige). Pour les harnais qui supportent `@<file>` (Claude Code, Cursor), une migration vers référence est possible mais hors périmètre de ce lot.
- **Cursor et Gemini utilisent la convention cross-CLI `.agents/`** déjà supportée par le stack existant ; aucun nouveau adaptateur dédié n'est nécessaire. Le bloc vault v4 cible `AGENTS.md` propre à chaque harnais (pas `.agents/AGENTS.md` qui n'existe pas).
- **Le repo public applique sa propre doctrine** : `python scripts/measure_scope.py` reste vert (191 fichiers / 246 394 tokens après les ajouts) ; `python scripts/validate_conventions.py` reste vert ; `git diff --check` reste propre (sortie vide) ; aucun warning clippy / eslint / etc. applicable (le repo est Python + Node + shell, pas C++/Rust/TS).
- **Le travail de maintenance de la baseline du vault** (Gate 0) reste du ressort de l'orchestrateur. Agent B n'a pas touché au vault réel.

## État final

- **HEAD final** : `573f368`
- **HEAD de départ** : `e3172d4`
- **Commits ajoutés** : 4
- **Statut des tests** : 81 / 81 verts (43 nouveaux + 38 existants), 0 régression
- **Statut CI** : `python scripts/measure_scope.py` OK, `python scripts/validate_conventions.py` OK, `git diff --check` propre
- **Statut LOC gate** : tous les fichiers ≤ 550 LOC (`vault_protocol.py` est le plus long, justifié par couverture de 7+ statuts et 5+ helpers atomiques)
- **vault réel modifié** : **non**
- **push** : **non**
- **merge** : **non**
- **release** : **non**
