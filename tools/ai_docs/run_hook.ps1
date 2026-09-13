# run_hook.ps1 - PostToolUse wrapper (Windows native).
# Reads one hook payload from stdin and delegates to update_on_edit.py next to
# this script. Always exits 0 so it never blocks the editor.
#
# Windows gives a redirected stdin to PowerShell in several shapes, and which
# one carries the bytes depends on whether the process has a console (a local
# terminal vs a CI service): the pipeline enumerator held the payload on the
# runners while [Console]::In was empty, and both were observed the other way
# around locally. The wrapper therefore tries every stream in turn and uses
# whichever has the JSON. A skip is reported on stderr, never silent.

$ErrorActionPreference = "SilentlyContinue"

function Read-HookPayload {
    # 1. The pipeline enumerator: PowerShell buffers redirected stdin for it.
    $text = $input | Out-String
    if ($text.Trim()) { return $text }
    # 2. The raw standard-input handle, before Console.In wraps it.
    try {
        $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput())
        $text = $reader.ReadToEnd()
        if ($text.Trim()) { return $text }
    } catch { }
    # 3. The console reader, for hosts where only that one is wired.
    try {
        $text = [Console]::In.ReadToEnd()
        if ($text.Trim()) { return $text }
    } catch { }
    return ""
}

$PAYLOAD = Read-HookPayload
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$UPDATE_SCRIPT = Join-Path $SCRIPT_DIR "update_on_edit.py"

if (-not $PAYLOAD.Trim()) {
    [Console]::Error.WriteLine("[ai_docs] PostToolUse hook received no payload on stdin")
    [Console]::Error.Flush()
    exit 0
}

$PY = $null
foreach ($candidate in @("python", "python3", "py")) {
    # `Get-Command` can return several matches (the real interpreter and the
    # WindowsApps execution alias); taking `.Source` off the array yields
    # nothing, and taking the alias yields a Store stub that exits 0 without
    # running anything. Every match is considered, and only a real .exe wins.
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
# Payload by file, not by pipe: PowerShell's pipe to a native executable is
# not byte-stable across host shapes (console-less runners mangled it), and
# the exact bytes are what the JSON parse needs.
$PAYLOAD_FILE = Join-Path ([System.IO.Path]::GetTempPath()) ("ai_docs_hook_" + [System.Guid]::NewGuid().ToString("N") + ".json")
try {
    [System.IO.File]::WriteAllText($PAYLOAD_FILE, $PAYLOAD, (New-Object System.Text.UTF8Encoding($false)))
    & $PY $UPDATE_SCRIPT --payload-file $PAYLOAD_FILE 2>&1 | Out-String | Write-Output
} finally {
    Remove-Item -LiteralPath $PAYLOAD_FILE -ErrorAction SilentlyContinue
}
exit 0