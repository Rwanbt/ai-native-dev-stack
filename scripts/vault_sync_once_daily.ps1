# vault_sync_once_daily.ps1 — Windows entry point for the once-a-day vault sync.
#
# The implementation is scripts/vault_sync_once_daily.py. The sentinel is
# written only when the sync actually succeeded, so a failed backup does not
# suppress the retry for the rest of the day.
#
# Usage:
#   pwsh -NoProfile -File scripts/vault_sync_once_daily.ps1
#   pwsh -NoProfile -File scripts/vault_sync_once_daily.ps1 -Vault 'D:\...' -Force

param(
    [string]$Vault,
    [switch]$Force
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$implementation = Join-Path $scriptDir "vault_sync_once_daily.py"

$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
    & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (-not $python) {
    Write-Error "No working Python 3.8+ found — vault NOT synced."
    exit 1
}

$arguments = @($implementation)
if ($Vault) { $arguments += @("--vault", $Vault) }
if ($Force) { $arguments += "--force" }

$env:PYTHONIOENCODING = "utf-8"
& $python @arguments
exit $LASTEXITCODE
