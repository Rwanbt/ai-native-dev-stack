# run_hook.ps1 - PostToolUse wrapper (Windows native).
# Reads one hook payload from stdin and delegates to update_on_edit.py next to
# this script. Always exits 0 so it never blocks the editor.
#
# stdin read order: the PowerShell pipeline enumerator first, [Console]::In as
# a fallback. With redirected input the two disagree depending on whether the
# process has a console (a local terminal vs a CI service): `[Console]::In`
# returned empty on the runners while `$input` held the payload, and the
# reverse was observed elsewhere. Whichever has the JSON wins; if neither
# does, the skip is reported on stderr instead of staying silent.
$ErrorActionPreference = "SilentlyContinue"
$PAYLOAD = $input | Out-String
if (-not $PAYLOAD.Trim()) {
    $PAYLOAD = [Console]::In.ReadToEnd()
}
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$UPDATE_SCRIPT = Join-Path $SCRIPT_DIR "update_on_edit.py"

if (-not $PAYLOAD.Trim()) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook received no payload on stdin")
    exit 0
}

$PY = $null
foreach ($candidate in @("python", "python3", "py")) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $found) { continue }
    # The WindowsApps entries are execution aliases for the Store stub: they
    # "exist", then do nothing and exit 0. A hook that silently does nothing
    # is the failure this prevents.
    if ($found.Source -like "*\WindowsApps\*") { continue }
    $PY = $found.Source
    break
}

if (-not $PY) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook found no usable Python on PATH")
    exit 0
}
if (-not (Test-Path $UPDATE_SCRIPT)) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook found no update_on_edit.py at $UPDATE_SCRIPT")
    exit 0
}
$env:PYTHONIOENCODING = "utf-8"
$PAYLOAD | & $PY $UPDATE_SCRIPT 2>&1 | Out-String | Write-Output
exit 0