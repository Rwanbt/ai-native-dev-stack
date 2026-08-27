# Scripts — Utilities AI Native Dev Stack

## vault_sync_once_daily.ps1

Synchronise le vault Obsidian une fois par jour (première session).

**Usage:**
```powershell
# Lancer au démarrage de session
pwsh -NoProfile -File vault_sync_once_daily.ps1
```

**Sorties:**
- `✅ déjà synchronisé aujourd'hui` → continuer sans commentaire
- `✅ synchronisé (YYYY-MM-DD)` → première session du jour
- `⚠️ DIVERGENCE` → signaler et attendre instruction

**Intégration CLAUDE.md global:**
Ajouter dans `~/.claude/CLAUDE.md` (section début de session):
```powershell
pwsh -NoProfile -File 'D:/App/ai-native-dev-stack/scripts/vault_sync_once_daily.ps1'
```

## vault_sync.ps1

Script de sync effectif (appelé par vault_sync_once_daily.ps1).
État actuel: placeholder — le vault `IA_Dev_Brain` est local uniquement (hors Git).

## loc_gate.ps1 — supprimé

Fusionné dans `hooks/pretool-loc-gate/run_gate.js`, seule implementation de la
regle LOC. Node stdlib, identique sur Linux/macOS/Windows, trois modes :

```bash
node hooks/pretool-loc-gate/run_gate.js <fichier>   # un fichier (hook PreToolUse)
node hooks/pretool-loc-gate/run_gate.js --staged    # fichiers git staged (pre-commit)
node hooks/pretool-loc-gate/run_gate.js --all       # scan complet du depot
```

Les seuils ne sont plus ecrits dans le script : ils viennent de `conventions.json`
a la racine du stack, que la CI maintient aligne sur `AGENTS.md`.

**Integration pre-commit** (`.git/hooks/pre-commit`, tout OS) :
```bash
node /chemin/vers/ai-native-dev-stack/hooks/pretool-loc-gate/run_gate.js --staged || exit 1
```
