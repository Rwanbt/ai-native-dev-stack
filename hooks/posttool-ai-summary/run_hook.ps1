# run_hook.ps1 - PostToolUse AI_SUMMARY generator (Windows native, global hook).
# Resolves the stack root from this file's location (hooks/posttool-ai-summary/),
# reads one hook payload from stdin, and delegates to the stack's
# tools/ai_docs/update_on_edit.py. Always exits 0 so it never blocks the editor.
#
# Windows gives a redirected stdin to PowerShell in several shapes, and which
# one carries the bytes depends on whether the process has a console (a local
# terminal vs a CI service). The wrapper therefore tries every stream in turn,
# hands the exact bytes to Python through a temp file (PowerShell's pipe to a
# native executable is not byte-stable across host shapes), and reports a skip
# on stderr instead of staying silent.
$ErrorActionPreference = "SilentlyContinue"

function Read-HookPayload {
    $text = $input | Out-String
    if ($text.Trim()) { return $text }
    try {
        $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput())
        $text = $reader.ReadToEnd()
        if ($text.Trim()) { return $text }
    } catch { }
    try {
        $text = [Console]::In.ReadToEnd()
        if ($text.Trim()) { return $text }
    } catch { }
    return ""
}

$PAYLOAD = Read-HookPayload
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$STACK_ROOT = (Resolve-Path (Join-Path $SCRIPT_DIR "..\..")).Path
$UPDATE_SCRIPT = Join-Path $STACK_ROOT "tools\ai_docs\update_on_edit.py"

if (-not $PAYLOAD.Trim()) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook received no payload on stdin")
    [Console]::Error.Flush()
    exit 0
}

$PY = $null
foreach ($candidate in @("python", "python3", "py")) {
    foreach ($found in @(Get-Command $candidate -All -ErrorAction SilentlyContinue)) {
        $path = $found.Source
        if (-not $path) { continue }
        if ($path -like "*\WindowsApps\*") { continue }
        if ($path -like "*.exe" -and (Test-Path $path)) { $PY = $path; break }
    }
    if ($PY) { break }
}

if (-not $PY) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook found no usable Python on PATH")
    [Console]::Error.Flush()
    exit 0
}
if (-not (Test-Path $UPDATE_SCRIPT)) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook found no update_on_edit.py at $UPDATE_SCRIPT")
    [Console]::Error.Flush()
    exit 0
}
$env:PYTHONIOENCODING = "utf-8"
$PAYLOAD_FILE = Join-Path ([System.IO.Path]::GetTempPath()) ("ai_docs_hook_" + [System.Guid]::NewGuid().ToString("N") + ".json")
try {
    [System.IO.File]::WriteAllText($PAYLOAD_FILE, $PAYLOAD, (New-Object System.Text.UTF8Encoding($false)))
    & $PY $UPDATE_SCRIPT --payload-file $PAYLOAD_FILE 2>&1 | Out-String | Write-Output
} finally {
    Remove-Item -LiteralPath $PAYLOAD_FILE -ErrorAction SilentlyContinue
}
exit 0