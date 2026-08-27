/**
 * run.js — SessionEnd memory saver.
 *
 * Appends one entry to LOG.md in the Obsidian vault.
 * Node.js stdlib only — zero external dependency.
 *
 * Usage: node run.js
 * Environment:
 *   OBSIDIAN_API_KEY  - Local REST API key (required; without it, no-op)
 *   OBSIDIAN_API_URL  - override endpoint (default: https://127.0.0.1:27124)
 *   SESSION_ID        - session id (optional)
 *   PROJECT_NAME      - active project name (optional)
 *   SESSION_SUMMARY   - session summary (optional)
 *
 * Appends via the API's POST verb rather than read-modify-write. The previous
 * implementation read LOG.md, concatenated, and PUT the whole file back —
 * which truncated the log to a single entry whenever the read failed (a failed
 * read and an empty file were indistinguishable), and lost entries whenever
 * two sessions ended at once.
 */

const path = require('path');
const { appendVaultFile, configured } = require(path.join(__dirname, '..', 'lib', 'obsidian_client'));

const SESSION_ID = process.env.SESSION_ID || 'unknown';
const PROJECT_NAME = process.env.PROJECT_NAME || '';
const SUMMARY = process.env.SESSION_SUMMARY || '';

const LOG_PATH = process.env.OBSIDIAN_LOG_PATH || 'LOG.md';

/** YYYY-MM-DD HH:MM in local time (the vault is a human-facing journal). */
function formatStamp() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} `
       + `${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function emit(metadata) {
  console.log(JSON.stringify({ metadata }));
}

async function main() {
  if (!configured()) {
    emit({ sessionSaveSkipped: 'OBSIDIAN_API_KEY not set' });
    return;
  }

  const stamp = formatStamp();
  const projectLine = PROJECT_NAME ? ` — [${PROJECT_NAME}]` : '';
  const summaryLine = SUMMARY ? `\n${SUMMARY}` : '';
  const entry = `\n## ${stamp}${projectLine}${summaryLine}\n\nSession: ${SESSION_ID}\n`;

  const res = await appendVaultFile(LOG_PATH, entry);

  if (!res.ok) {
    // Report the failure; never fall back to overwriting the log.
    emit({ sessionSaveError: res.error, logPath: LOG_PATH });
    return;
  }

  emit({ sessionSaved: stamp, project: PROJECT_NAME, logPath: LOG_PATH });
}

main().catch((err) => emit({ sessionSaveError: err.message }));
