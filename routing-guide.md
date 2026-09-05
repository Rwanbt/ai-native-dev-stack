# Routing Guide — Quel agent pour quelle tâche

> Ce guide est une adaptation universelle de la section "Subagent vs lecture directe" du CLAUDE.md global d'Erwan Barat. Il fonctionne pour tout agent IA : Mavis, Claude Code, Codex, Cursor, etc.

---

## Règle 0 — Diagnostic avant correctif

**Toujours.** Avant de corriger, lire les fichiers impactés, identifier la cause racine, vérifier les call sites. Ne proposer un correctif que si le diagnostic est complet. Si le risque de régression est non nul et non maîtrisé, proposer sans appliquer et expliquer ce qu'il faut vérifier.

---

## Règle 1 — Estimer le périmètre

### Commandes d'estimation

**PowerShell (Windows):**
```powershell
# Estimer taille tokens (÷4 = tokens estimés)
Get-ChildItem -Path . -Recurse -Include *.py,*.rs,*.cpp,*.c,*.h,*.hpp,*.ts,*.js `
  -Exclude node_modules,.git,target,build,dist,vendor `
  | Get-Content | Measure-Object -Line

# Compter les fichiers source
Get-ChildItem -Path . -Recurse -Include *.py,*.rs,*.cpp,*.ts -Exclude node_modules,.git `
  | Measure-Object | Select-Object -ExpandProperty Count
```

**Bash (Linux/macOS/Git Bash):**
```bash
# Taille tokens estimés (÷4, variance ±20%)
git ls-files | grep -E '\.(py|rs|cpp|c|h|hpp|ts|js|go)$' | xargs wc -c 2>/dev/null | tail -1

# Nombre de fichiers source
git ls-files | grep -E '\.(py|rs|cpp|c|h|hpp|ts|js)$' | wc -l

# Fallback hors git
find . -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/target/*' -not -path '*/build/*' \
  \( -name '*.py' -o -name '*.rs' -o -name '*.cpp' -o -name '*.ts' \) \
  | xargs wc -c 2>/dev/null | tail -1
```

---

## Règle 2 — Taille → Mode de travail

```
┌─────────────────────────────┐
│  < 50k tokens source       │
│  → Lecture DIRECTE          │
│  → Couverture 100%          │
│  → agent principal only      │
└─────────────────────────────┘
              ↓
┌─────────────────────────────┐
│  50k – 150k tokens          │
│  → Cartographie AST/ctags   │
│  → Lecture ciblée           │
│  → Couverture à déclarer    │
└─────────────────────────────┘
              ↓
┌─────────────────────────────┐
│  > 150k tokens              │
│  → Team plan multi-phases   │
│  → Phase 1: cartographie   │
│  → Phase 2: lecture directe │
│  → Phase 3: synthèse       │
└─────────────────────────────┘
```

---

## Règle 3 — Mode par type d'intention

| Signal dans la demande | Mode | Stratégie |
|----------------------|------|-----------|
| "Où est X ?", "trouver Y" | **Lookup** | Subagent Explore |
| "Comment fonctionne X ?" | **Understanding** | Subagent + lecture ciblée |
| "Revue", "analyse l'architecture" | **Review** | Synthèse centrale + liste fichiers lus/non lus |
| "Exhaustif", "complet", "rien ne manque", "audit" | **Audit** | Workflow manifest-driven + coverage vérifié obligatoire |

**Signal de complexité secondaire** : si `tokens < 50k` mais `fichiers > 100` → prioriser un tour de clarification.

**Tour de clarification type:**
```
"Je vois ~X tokens dans Y fichiers. Quel niveau d'analyse ?
[A] Vue d'ensemble rapide (Explore agent, ~2k tokens)
[B] Analyse ciblée (lecture directe, ~10k tokens)
[C] Audit exhaustif (lecture séquentielle, ~X tokens, coverage vérifié)"
```

---

## Règle 4 — Quand créer un team plan

Un team plan (multi-session parallèle + verifiers) est justifié quand:

1. **≥ 3 tracks parallèles** et indépendantes (ex: UI + data layer + API)
2. **Vérification indépendante** nécessaire (sécurité, permissions, calculs, données critiques)
3. **Haute valeur d'erreur** (un bug aurait un coût important)
4. **Chaîne de livraison multi-étapes** (research → analyze → write → verify)

### Patterns de team plan

```
[impl-track-1] --\
[impl-track-2] --+--> [integration-gate]
[impl-track-3] --/

tracks parallèles: pas de depends_on entre elles
integration gate: attend toutes les tracks avant de vérifier
```

---

## Règle 5 — Quand utiliser un subagent / worker

| Cas | Utiliser subagent ? |
|-----|---------------------|
| Exploration de codebase inconnu | Oui — lecture en profondeur |
| Tâches indépendantes sur fichiers différents | Oui — exécution parallèle |
| Code review adversarial | Oui — regard neuf |
| Décision de routing elle-même | Non — agent principal |

### Anti-patterns

- **Ne PAS utiliser un subagent pour un Audit exhaustif** — la lecture directe dans le contexte principal garantit 100% de coverage
- **Ne PAS créer un team plan pour une tâche < 1h** — le overhead de coordination dépasse le gain

---

## Règle 6 — Checklist de routing avant de commencer

```
1. Taille du périmètre ? (__ tokens / __ fichiers)
2. Intent ? (lookup | understanding | review | audit | direct-edit)
3. Mode ?
   [ ] Directe (< 50k tokens, audit < scope)
   [ ] Subagent (< 150k tokens, exploration ciblée)
   [ ] Team plan (> 150k tokens ou ≥ 3 tracks)
4. Si team plan: tracks ? dépendances ? verifiers ?
5. Si directe: coverage attendu ? (% fichiers / tokens)
```

---

## Exemples concrets (projets d'Erwan)

| Projet | Taille | Intent | Mode |
|--------|--------|--------|------|
| Seno Materia (~15k LOC, Rust) | < 50k | "ajoute la GUI" | Directe |
| VECTORA (~100k LOC, Rust) | 50k-150k | "analyse graph-engine" | Subagent + lecture ciblée |
| Seno DAW (~300k LOC, C++/Rust) | > 150k | "audit thread safety audio" | Team plan |
| HireLens (~20k LOC, Rust) | < 50k | "ajoute provider Ollama" | Directe |
| AI Native Dev Stack (~2k LOC, Python) | < 50k | "universalistion hooks" | Directe |

---

## Annexe — Seuils LOC pour la qualité (depuis CLAUDE.md)

| Métrique | Cible | Alerte | Bloquant |
|----------|-------|--------|----------|
| LOC / fichier | ≤ 500 | > 800 | > 1500 |
| LOC / fonction | ≤ 50 | > 100 | > 200 |
| Complexité cyclomatique | ≤ 10 | > 15 | > 25 |
| LOC / PR | ≤ 400 | — | Découper |

---

*Source: adapté d'un CLAUDE.md personnel § "Règle — Subagent vs lecture directe (v2.1)"*
*Dernière mise à jour: 2026-06-15*
