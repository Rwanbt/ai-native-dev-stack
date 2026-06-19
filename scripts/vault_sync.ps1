# vault_sync.ps1
# Sync vault Obsidian: pull si modifications, push si divergence
# Copié depuis D:\scripts\vault_sync.ps1
# IMPORTANT: le vault D:\Documents\Obsidian\IA_Dev_Brain est HORS GIT
# Ce script est préparé pour le cas où le vault serait synchronisé via Git
# Configuration actuelle: vault local uniquement (pas de sync Git)

$VAULT_PATH = "D:\Documents\Obsidian\IA_Dev_Brain"
$LAST_SYNC = Join-Path $PSScriptRoot "vault_last_sync_date.txt"

if (-not (Test-Path $VAULT_PATH)) {
    Write-Host "vault: IA_Dev_Brain introuvable — skip"
    exit 0
}

# État actuel: vault local uniquement, pas de Git sync
# Ce script est un placeholder pour le moment
# TODO: intégrer Obsidian Git plugin ou script de backup automatique
Write-Host "vault: sync vault local ($VAULT_PATH) — operation non configuree (vault hors Git)"
exit 0
