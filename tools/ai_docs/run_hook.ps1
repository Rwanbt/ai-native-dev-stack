# run_hook.ps1 - Claude Code PostToolUse wrapper (Windows native).
# Reads one hook payload from redirected stdin and delegates to
# update_on_edit.py next to this script. Always exits 0 so it never blocks the
# editor; when no usable Python is found it skips silently rather than failing
# the tool call.
# [Console]::In, not Get-Content: PowerShell 5.1's Get-Content has a mandatory
# -Path and does not read redirected stdin on its own.
$ErrorActionPreference = "SilentlyContinue"
$PAYLOAD = [Console]::In.ReadToEnd()
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$UPDATE_SCRIPT = Join-Path $SCRIPT_DIR "update_on_edit.py"

$PY = $null
foreach ($candidate in @("python", "python3", "py")) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) { $PY = $found.Source; break }
}

if ($PY -and (Test-Path $UPDATE_SCRIPT) -and $PAYLOAD) {
    $env:PYTHONIOENCODING = "utf-8"
    $PAYLOAD | & $PY $UPDATE_SCRIPT 2>&1 | Out-String | Write-Output
}
exit 0