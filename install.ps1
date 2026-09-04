# install.ps1 — Windows-native bootstrap for the AI-Native Dev Stack.
#
# It finds a Python and hands over to install.py, which hands over to the
# lifecycle manager. It holds no lifecycle logic of its own: the single
# authority for installing, switching, uninstalling and updating is the
# lifecycle CLI (ADR-0009).
#
# Usage:
#   pwsh -NoProfile -File install.ps1                              # asks which profile
#   pwsh -NoProfile -File install.ps1 -Profile standard
#   pwsh -NoProfile -File install.ps1 -Profile verified -DryRun
#   pwsh -NoProfile -File install.ps1 -Project C:\path\to\project

param(
    [ValidateSet("standard", "verified")]
    [string]$Profile,
    [Alias("ProjectRoot")]
    [string]$Project = (Get-Location).Path,
    [switch]$DryRun,
    [switch]$WithGstack,
    [string]$GstackRef
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $scriptDir "install.py"

# The lifecycle CLI needs 3.11+; the AI-docs tooling it installs still runs on
# 3.8+. Only the interpreter that runs the CLI is gated here.
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $command) { continue }
    & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}

if (-not $python) {
    Write-Error "No working Python 3.11+ found. Install Python from python.org and re-run."
    exit 1
}

$arguments = @($installer, "--project", $Project)
if ($Profile)    { $arguments += @("--profile", $Profile) }
if ($DryRun)     { $arguments += "--dry-run" }
if ($WithGstack) { $arguments += "--with-gstack" }
if ($GstackRef)  { $arguments += @("--gstack-ref", $GstackRef) }

$env:PYTHONIOENCODING = "utf-8"
& $python @arguments
exit $LASTEXITCODE
