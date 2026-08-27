# setup-agents.ps1 — Windows-native entry point for the global stack installer.
#
# Same installer as setup-agents.sh (scripts/install_agents.py); this script
# exists so Windows users do not need Git Bash or WSL.
#
# Usage:
#   pwsh -NoProfile -File scripts/setup-agents.ps1
#   pwsh -NoProfile -File scripts/setup-agents.ps1 -DryRun
#   pwsh -NoProfile -File scripts/setup-agents.ps1 -Check

param(
    [switch]$DryRun,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $scriptDir "install_agents.py"

if (-not (Test-Path $installer)) {
    Write-Error "Installer not found: $installer"
    exit 1
}

# Find a Python 3.8+ that actually runs (skips Microsoft Store stubs).
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $command) { continue }
    & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}

if (-not $python) {
    Write-Error "No working Python 3.8+ found. Install Python from python.org and re-run."
    exit 1
}

$arguments = @($installer)
if ($DryRun) { $arguments += "--dry-run" }
if ($Check)  { $arguments += "--check" }

$env:PYTHONIOENCODING = "utf-8"
& $python @arguments
exit $LASTEXITCODE
