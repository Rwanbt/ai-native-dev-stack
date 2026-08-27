/**
 * run_gate.js — LOC gate. PreToolUse hook, pre-commit check, or full-repo scan.
 *
 * Node.js stdlib only — zero external dependency, runs identically on
 * Linux, macOS and Windows (no shell-out to a platform-specific interpreter).
 *
 * This is the ONLY implementation of the LOC rule. Thresholds come from
 * conventions.json at the stack root, which CI keeps in sync with AGENTS.md.
 *
 * Usage:
 *   node run_gate.js <file>     check one file   (PreToolUse hook)
 *   node run_gate.js --staged   check git staged files (pre-commit)
 *   node run_gate.js --all      check the whole repo
 *
 * Output contract:
 *   Mavis PreToolUse       — { _abort: { reason } } on block
 *   Claude Code / Codex    — exit code 1 on block; `reason` is always emitted
 *                            so the agent sees WHY, warnings included.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const DEFAULTS = {
  file_size: { new_file_warning: 500, existing_file_warning: 800, blocking: 1500 },
  scan_extensions: ['.py', '.rs', '.cpp', '.c', '.h', '.hpp', '.ts', '.js', '.go'],
  exclude_dirs: ['node_modules', '.git', 'target', 'build', 'dist', 'vendor',
                 '.venv', 'venv', '__pycache__', '.cache'],
};

/** Walk up from this script to find conventions.json (the stack root marker). */
function loadConventions() {
  let dir = __dirname;
  for (let depth = 0; depth < 6; depth++) {
    const candidate = path.join(dir, 'conventions.json');
    if (fs.existsSync(candidate)) {
      try {
        return JSON.parse(fs.readFileSync(candidate, 'utf8'));
      } catch {
        break; // malformed — fall through to defaults rather than crash the hook
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return DEFAULTS;
}

const CONV = loadConventions();
const T = { ...DEFAULTS.file_size, ...(CONV.file_size || {}) };
const EXTENSIONS = CONV.scan_extensions || DEFAULTS.scan_extensions;
const EXCLUDE_DIRS = CONV.exclude_dirs || DEFAULTS.exclude_dirs;

function countLines(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return content.length === 0 ? 0 : content.split(/\r?\n/).length;
  } catch {
    return 0;
  }
}

function isExcluded(filePath) {
  const parts = path.resolve(filePath).split(/[/\\]/);
  return EXCLUDE_DIRS.some(d => parts.includes(d));
}

function hasScannedExtension(filePath) {
  return EXTENSIONS.includes(path.extname(filePath).toLowerCase());
}

/**
 * Check one file.
 * @returns {{level: 'pass'|'warning'|'blocked', reason: string, lines: number, file: string}}
 */
function checkFile(filePath) {
  const absPath = path.resolve(filePath);
  const exists = fs.existsSync(absPath);
  const lines = countLines(absPath);

  if (lines > T.blocking) {
    return {
      level: 'blocked', file: absPath, lines, threshold: T.blocking,
      reason: `LOC GATE: ${absPath} is ${lines} LOC (blocking limit: ${T.blocking}). ` +
              `Refactor before modifying — see AGENTS.md "Code structure".`,
    };
  }
  if (!exists && lines > T.new_file_warning) {
    return {
      level: 'warning', file: absPath, lines, threshold: T.new_file_warning, type: 'new_file',
      reason: `LOC GATE: new file ${absPath} at ${lines} LOC (>${T.new_file_warning}). ` +
              `Propose a decomposition now — see AGENTS.md "Code structure".`,
    };
  }
  if (exists && lines > T.existing_file_warning) {
    return {
      level: 'warning', file: absPath, lines, threshold: T.existing_file_warning, type: 'existing',
      reason: `LOC GATE: existing file ${absPath} at ${lines} LOC (>${T.existing_file_warning}). ` +
              `Propose extracting its secondary responsibilities — see AGENTS.md "Code structure".`,
    };
  }
  return { level: 'pass', file: absPath, lines, reason: '' };
}

function stagedFiles() {
  try {
    const out = execFileSync('git', ['diff', '--cached', '--name-only', '--diff-filter=ACM'],
                             { encoding: 'utf8' });
    return out.split(/\r?\n/).filter(Boolean);
  } catch {
    return [];
  }
}

function walkRepo(dir, acc = []) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (!EXCLUDE_DIRS.includes(e.name)) walkRepo(full, acc);
    } else if (hasScannedExtension(full)) {
      acc.push(full);
    }
  }
  return acc;
}

/** Report a batch (--staged / --all): human-readable lines, exit 1 if anything blocks. */
function reportBatch(files) {
  const results = files
    .filter(f => !isExcluded(f) && hasScannedExtension(f))
    .map(checkFile)
    .filter(r => r.level !== 'pass');

  for (const r of results) console.log(`[${r.level.toUpperCase()}] ${r.reason}`);

  const blocked = results.filter(r => r.level === 'blocked');
  if (blocked.length > 0) {
    console.log(`\nLOC GATE: ${blocked.length} file(s) over the blocking limit.`);
    process.exit(1);
  }
  console.log(`LOC gate: ${files.length} file(s) checked, ${results.length} warning(s), 0 blocking.`);
}

function main() {
  const arg = process.argv[2];

  if (arg === '--staged') return reportBatch(stagedFiles());
  if (arg === '--all') return reportBatch(walkRepo(process.cwd()));

  if (!arg) {
    console.log(JSON.stringify({ metadata: { locGate: 'no_file_specified' } }));
    return;
  }

  // Single-file mode — the PreToolUse hook contract.
  // The rule is about source structure (AGENTS.md "Code structure"), so a long
  // CHANGELOG, dataset or generated file must not block an edit. Reported in
  // metadata rather than skipped silently, so an unexpected extension is visible.
  if (!hasScannedExtension(arg)) {
    console.log(JSON.stringify({
      metadata: {
        locGate: 'skipped',
        file: path.resolve(arg),
        reason_skipped: `extension ${path.extname(arg) || '(none)'} is not in conventions.json > scan_extensions`,
      },
    }));
    return;
  }

  const r = checkFile(arg);
  const metadata = { locGate: r.level, file: r.file, lines: r.lines };
  if (r.threshold) metadata.threshold = r.threshold;
  if (r.type) metadata.type = r.type;

  if (r.level === 'blocked') {
    console.log(JSON.stringify({ _abort: { reason: r.reason }, metadata }));
    process.exit(1);
  }

  // Warnings must reach the agent too: emit `reason`, not just metadata.
  console.log(JSON.stringify(r.level === 'warning' ? { reason: r.reason, metadata } : { metadata }));
}

main();
