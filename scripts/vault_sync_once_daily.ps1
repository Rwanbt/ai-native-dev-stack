# vault_sync_once_daily.ps1
# Sync vault Obsidian une fois par jour (première session de la journee)
# Copie depuis D:\scripts\vault_sync_once_daily.ps1
# Chemin du vault: D:\Documents\Obsidian\IA_Dev_Brain

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$SCRIPT_SYNC = Join-Path $SCRIPT_DIR "vault_sync.ps1"
$SENTINEL = Join-Path $SCRIPT_DIR "vault_last_sync_date.txt"
$TODAY = (Get-Date -Format "yyyy-MM-dd")

# Skip si deja synchronise aujourd'hui
if ((Test-Path $SENTINEL) -and ((Get-Content $SENTINEL -Raw).Trim() -eq $TODAY)) {
    Write-Host "vault: deja synchronise aujourd'hui ($TODAY) — skip"
    exit 0
}

# Premiere session de la journee → sync
if (Test-Path $SCRIPT_SYNC) {
    & $SCRIPT_SYNC
} else {
    Write-Host "vault: vault_sync.ps1 introuvable — skip"
    exit 1
}

# Marquer la date apres sync reussi
Set-Content -Path $SENTINEL -Value $TODAY
Write-Host "vault: synchronise ($TODAY)"
exit 0
