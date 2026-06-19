# run_hook.ps1 — PostToolUse AI_SUMMARY Generator (Windows natif)
# Wrapper PowerShell pour le hook PostToolUse.

$INPUT = Get-Content -Raw
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$STACK_ROOT = (Resolve-Path "$SCRIPT_DIR\..\..\..").Path
$UPDATE_SCRIPT = Join-Path $STACK_ROOT "tools\ai_docs\update_on_edit.py"

# Trouver un Python
$PY = $null
foreach ($p in @("python", "python3", "py", "C:\Python312\python.exe", "C:\Python311\python.exe")) {
    $pyCmd = Get-Command $p -ErrorAction SilentlyContinue
    if ($pyCmd) { $PY = $pyCmd.Source; break }
}

if ($PY -and (Test-Path $UPDATE_SCRIPT)) {
    $result = @($INPUT | & $PY $UPDATE_SCRIPT 2>&1 | Out-String)
    if ($result) { Write-Output $result }
} else {
    # Silent skip
}

exit 0
