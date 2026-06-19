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

## loc_gate.ps1

Gate LOC pour fichiers source — vérifie contre les seuils CLAUDE.md.

**Usage:**
```powershell
# Check un fichier
pwsh -NoProfile -File scripts/loc_gate.ps1 -FilePath "src/main.rs"

# Check fichiers git staged
pwsh -NoProfile -File scripts/loc_gate.ps1 -Staged

# Check tous les fichiers source (scan)
pwsh -NoProfile -File scripts/loc_gate.ps1
```

**Seuils:**
| Condition | Action |
|-----------|--------|
| > 500 LOC (nouveau) | Warning — proposer décomposition |
| > 800 LOC (existant) | Warning — proposer extraction |
| > 1500 LOC | **ERROR** — refactoring obligatoire |

**Intégration pre-commit:**
```powershell
# Dans .git/hooks/pre-commit
pwsh -NoProfile -File D:/App/ai-native-dev-stack/scripts/loc_gate.ps1 -Staged
if ($LASTEXITCODE -ne 0) { exit 1 }
```
