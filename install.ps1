# install.ps1 — Windows-native entry point for the per-project installer.
#
# Same installer as install.sh (install.py); this script exists so Windows
# users do not need Git Bash or WSL.
#
# Usage:
#   pwsh -NoProfile -File install.ps1
#   pwsh -NoProfile -File install.ps1 -ProjectRoot C:\path\to\project -WithGstack
#   pwsh -NoProfile -File install.ps1 -DryRun

param(
    [string]$ProjectRoot = (Get-Location).Path,
    [switch]$WithGstack,
    [string]$GstackRef,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $scriptDir "install.py"

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

$arguments = @($installer, "--project-root", $ProjectRoot)
if ($WithGstack) { $arguments += "--with-gstack" }
if ($GstackRef)  { $arguments += @("--gstack-ref", $GstackRef) }
if ($DryRun)     { $arguments += "--dry-run" }

$env:PYTHONIOENCODING = "utf-8"
& $python @arguments
exit $LASTEXITCODE
