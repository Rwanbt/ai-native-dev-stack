# loc_gate.ps1 — LOC Gate pour PreToolUse / pre-commit
# Vérifie la taille des fichiers source contre les seuils CLAUDE.md
# Seuils:
#   > 500 LOC (nouveau fichier)  → WARNING
#   > 800 LOC (fichier existant) → WARNING
#   > 1500 LOC (tout fichier)    → ERROR (bloquant)

param(
    [Parameter(Mandatory=$false)]
    [string]$FilePath,

    [Parameter(Mandatory=$false)]
    [switch]$Staged  # Check git staged files
)

$THRESHOLDS = @{
    NEW_WARNING = 500
    EXISTING_WARNING = 800
    BLOCKING = 1500
}

$EXTENSIONS = @("*.py", "*.rs", "*.cpp", "*.c", "*.h", "*.hpp", "*.ts", "*.js", "*.go", "*.cs", "*.fs", "*.swift")
$EXCLUDE_DIRS = @("node_modules", ".git", "target", "build", "dist", "vendor", ".venv", "venv", "__pycache__", ".cache")

function Get-LineCount {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return 0 }
    try {
        (Get-Content $Path -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    } catch { 0 }
}

function Test-InExcludeDir {
    param([string]$Dir)
    foreach ($ex in $EXCLUDE_DIRS) {
        if ($Dir -match "[/\\]$ex[/\\]?$") { return $true }
    }
    $false
}

function Invoke-GateCheck {
    param([string]$Path)

    $absPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    $exists = Test-Path $absPath
    $lines = Get-LineCount $absPath
    $isNew = -not $exists

    if ($lines -gt $THRESHOLDS.BLOCKING) {
        Write-Error "[LOC GATE] BLOQUANT: $absPath ($lines LOC > $($THRESHOLDS.BLOCKING)) — Refactoring obligatoire."
        return $false
    }

    if ($isNew -and $lines -gt $THRESHOLDS.NEW_WARNING) {
        Write-Warning "[LOC GATE] WARNING: nouveau fichier $absPath ($lines LOC > $($THRESHOLDS.NEW_WARNING)) — proposer décomposition."
        return $true  # Warning seulement
    }

    if ($exists -and $lines -gt $THRESHOLDS.EXISTING_WARNING) {
        Write-Warning "[LOC GATE] WARNING: fichier existant $absPath ($lines LOC > $($THRESHOLDS.EXISTING_WARNING)) — proposer extraction."
        return $true
    }

    return $true  # Pass
}

$global:blocked = $false

if ($Staged) {
    # Check git staged files
    try {
        $staged = git diff --cached --name-only --diff-filter=ACM 2>$null
        if ($staged) {
            foreach ($f in $staged) {
                $isExcluded = $false
                foreach ($dir in $EXCLUDE_DIRS) {
                    if ($f -match $dir) { $isExcluded = $true; break }
                }
                if ($isExcluded) { continue }
                if (-not (Invoke-GateCheck $f)) { $global:blocked = $true }
            }
        }
    } catch { }
} elseif ($FilePath) {
    if (-not (Invoke-GateCheck $FilePath)) { $global:blocked = $true }
} else {
    # Check tous les fichiers source
    foreach ($ext in $EXTENSIONS) {
        Get-ChildItem -Recurse -Include $ext -File | ForEach-Object {
            if (-not (Test-InExcludeDir $_.DirectoryName)) {
                if (-not (Invoke-GateCheck $_.FullName)) { $global:blocked = $true }
            }
        }
    }
}

if ($global:blocked) { exit 1 } else { exit 0 }
