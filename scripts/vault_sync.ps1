# vault_sync.ps1 — Windows entry point for the vault sync.
#
# The implementation is scripts/vault_sync.py (one cross-platform version).
# This script only locates Python and delegates.
#
# Usage:
#   pwsh -NoProfile -File scripts/vault_sync.ps1 -Vault 'D:\Documents\Obsidian\MyVault'
#   pwsh -NoProfile -File scripts/vault_sync.ps1 -DryRun
#
# Without -Vault, the vault path comes from $env:OBSIDIAN_VAULT.

param(
    [string]$Vault,
    [switch]$DryRun,
    [switch]$AllowBranch
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$implementation = Join-Path $scriptDir "vault_sync.py"

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
if ($Vault)       { $arguments += @("--vault", $Vault) }
if ($DryRun)      { $arguments += "--dry-run" }
if ($AllowBranch) { $arguments += "--allow-branch" }

$env:PYTHONIOENCODING = "utf-8"
& $python @arguments
exit $LASTEXITCODE
