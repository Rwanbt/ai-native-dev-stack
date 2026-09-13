#Requires -Version 5.1
# OPTIONAL HIGH-ASSURANCE HARDENING (EXPERIMENTAL) - not part of the normal installation.
# Runs UNDER the dedicated workload principal (scheduled task). Writes results only.
# Every path is supplied by the operator (argument or environment); no machine
# default is baked in, because this repository is public and the maintainer's
# layout is not a contract.
param(
    [string]$OutputPath = $env:AINATIVE_ENFORCED_RESULTS,
    [string]$WorkspacePath = $env:AINATIVE_ENFORCED_WORKSPACE,
    [string]$VaultPath = $env:OBSIDIAN_VAULT,
    [string]$AuthorityStorePath = $env:AINATIVE_ENFORCED_AUTHORITY,
    [string]$ObsidianCredentialsPath = $env:AINATIVE_ENFORCED_OBSIDIAN_CREDENTIALS
)
if (-not $OutputPath) { throw "OutputPath is required (or set AINATIVE_ENFORCED_RESULTS). This script carries no machine defaults." }

$results = @()
function Record-Test([string]$Name, [string]$Path, [string]$Mode) {
    $outcome = "DENIED"
    $detail = ""
    try {
        if ($Mode -eq "read") {
            if (Test-Path -LiteralPath $Path -PathType Container) {
                Get-ChildItem -LiteralPath $Path -ErrorAction Stop | Select-Object -First 1 | Out-Null
            } else {
                [System.IO.File]::ReadAllBytes($Path) | Out-Null
            }
        } elseif ($Mode -eq "write") {
            $target = Join-Path $Path ("ainative-write-probe-" + [guid]::NewGuid().ToString("N") + ".tmp")
            [System.IO.File]::WriteAllText($target, "probe")
            Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
        }
        $outcome = "ALLOWED"
    } catch {
        $detail = $_.Exception.GetType().Name
    }
    $script:results += [pscustomobject]@{ test = $Name; path = $Path; mode = $Mode; result = $outcome; detail = $detail }
}

Record-Test "workspace-read" $WorkspacePath "read"
Record-Test "workspace-write" $WorkspacePath "write"
Record-Test "raw-vault-read" $VaultPath "read"
Record-Test "raw-vault-write" $VaultPath "write"
Record-Test "authority-store-read" $AuthorityStorePath "read"
Record-Test "obsidian-credentials-read" $ObsidianCredentialsPath "read"

$child = Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-NonInteractive", "-Command",
    "try { Get-ChildItem -LiteralPath '$VaultPath' -ErrorAction Stop | Select-Object -First 1 | Out-Null; exit 10 } catch { exit 20 }"
) -PassThru -Wait -WindowStyle Hidden
$grandchild = Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-NonInteractive", "-Command",
    "try { [System.IO.File]::ReadAllBytes('$ObsidianCredentialsPath') | Out-Null; exit 10 } catch { exit 20 }"
) -PassThru -Wait -WindowStyle Hidden

$childResult = "ALLOWED"
if ($child.ExitCode -eq 20) { $childResult = "DENIED" }
$grandchildResult = "ALLOWED"
if ($grandchild.ExitCode -eq 20) { $grandchildResult = "DENIED" }
$results += [pscustomobject]@{ test = "child-process-vault-read"; path = $VaultPath; mode = "read"; result = $childResult; detail = "exit=$($child.ExitCode)" }
$results += [pscustomobject]@{ test = "grandchild-process-credentials-read"; path = $ObsidianCredentialsPath; mode = "read"; result = $grandchildResult; detail = "exit=$($grandchild.ExitCode)" }

$payload = [pscustomobject]@{
    principal = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    recorded_at = (Get-Date).ToUniversalTime().ToString("o")
    results = $results
}
$directory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
[System.IO.File]::WriteAllText($OutputPath, ($payload | ConvertTo-Json -Depth 5))