/**
 * pretool-loc-gate.js — PreToolUse LOC Gate
 *
 * Vérifie la taille d'un fichier avant modification.
 * Node.js stdlib uniquement — zéro dépendance externe.
 *
 * Usage: node run.js <chemin_fichier>
 *
 * Seuils (depuis CLAUDE.md global):
 *   > 500 LOC (nouveau fichier)  → warning
 *   > 800 LOC (fichier existant) → warning
 *   > 1500 LOC (tout fichier)   → BLOCK (exit 1 + reason)
 *
 * Mavis PreToolUse: retourne { _abort: { reason: "..." } }
 * Claude Code / Codex: exit code 1 = bloquant, affiche le reason
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const THRESHOLDS = {
  NEW_FILE_WARNING: 500,
  EXISTING_FILE_WARNING: 800,
  BLOCKING: 1500,
};

function countLines(filePath) {
  try {
    // PowerShell pour compatibilité Windows-native
    const result = execSync(
      `powershell.exe -NoProfile -Command "(Get-Content '${filePath.replace(/'/g, "''")}' -ErrorAction SilentlyContinue | Measure-Object -Line).Lines"`,
      { encoding: 'utf8', timeout: 5000 }
    );
    const lines = parseInt(result.trim(), 10);
    return isNaN(lines) ? 0 : lines;
  } catch {
    return 0;
  }
}

function main() {
  const filePath = process.argv[2];
  if (!filePath) {
    console.log(JSON.stringify({ metadata: { locGate: 'no_file_specified' } }));
    return;
  }

  const absPath = path.resolve(filePath);
  const exists = fs.existsSync(absPath);
  const lines = countLines(absPath);

  const isNewFile = !exists;

  if (lines > THRESHOLDS.BLOCKING) {
    const reason = `LOC GATE: ${absPath} a ${lines} LOC (limite bloquante: ${THRESHOLDS.BLOCKING}). Refactoring obligatoire avant modification. (Règle CLAUDE.md)`;
    console.log(JSON.stringify({
      _abort: { reason },
      metadata: { locGate: 'blocked', file: absPath, lines, threshold: THRESHOLDS.BLOCKING }
    }));
    process.exit(1);
  }

  if (isNewFile && lines > THRESHOLDS.NEW_FILE_WARNING) {
    const reason = `LOC GATE: nouveau fichier ${absPath} à ${lines} LOC (>${THRESHOLDS.NEW_FILE_WARNING}). Proposer une décomposition immédiate.`;
    console.log(JSON.stringify({
      metadata: { locGate: 'warning', file: absPath, lines, threshold: THRESHOLDS.NEW_FILE_WARNING, type: 'new_file' }
    }));
    process.exit(0); // Warning seulement, ne bloque pas
  }

  if (exists && lines > THRESHOLDS.EXISTING_FILE_WARNING) {
    const reason = `LOC GATE: fichier existant ${absPath} à ${lines} LOC (>${THRESHOLDS.EXISTING_FILE_WARNING}). Proposer extraction des responsabilités secondaires.`;
    console.log(JSON.stringify({
      metadata: { locGate: 'warning', file: absPath, lines, threshold: THRESHOLDS.EXISTING_FILE_WARNING, type: 'existing' }
    }));
    process.exit(0);
  }

  console.log(JSON.stringify({
    metadata: { locGate: 'pass', file: absPath, lines }
  }));
}

main();
