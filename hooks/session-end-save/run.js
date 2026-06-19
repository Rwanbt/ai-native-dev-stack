/**
 * session-end-save.js — SessionEnd Memory Saver
 *
 * Appende une entrée LOG.md à la fin de session.
 * Node.js stdlib uniquement — zéro dépendance externe.
 *
 * Usage: node run.js
 * Variables d'environnement:
 *   SESSION_ID - ID de session (optionnel)
 *   PROJECT_NAME - Nom du projet actif (optionnel)
 *   SESSION_SUMMARY - Résumé de session (optionnel)
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

// Obsidian Local REST API key — read from the environment, never hardcoded.
// Set OBSIDIAN_API_KEY in your shell/agent config (see README.md).
const API_KEY = process.env.OBSIDIAN_API_KEY || '';
const VAULT_BASE = process.env.OBSIDIAN_API_URL || 'http://127.0.0.1:27123';

const SESSION_ID = process.env.SESSION_ID || 'unknown';
const PROJECT_NAME = process.env.PROJECT_NAME || '';
const SUMMARY = process.env.SESSION_SUMMARY || '';

/**
 * Lit un fichier du vault via l'API REST locale.
 */
async function readVaultFile(vaultPath) {
  return new Promise((resolve) => {
    const url = `${VAULT_BASE}/vault/?path=${encodeURIComponent(vaultPath)}`;
    const options = { headers: { 'Authorization': `Bearer ${API_KEY}` } };
    http.get(url, options, (res) => {
      if (res.statusCode !== 200) { resolve(''); return; }
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
      res.on('error', () => resolve(''));
    }).on('error', () => resolve(''));
  });
}

/**
 * Écrit un fichier dans le vault via l'API REST locale.
 */
async function writeVaultFile(vaultPath, content) {
  return new Promise((resolve) => {
    const url = `${VAULT_BASE}/vault/`;
    const body = JSON.stringify({
      path: vaultPath,
      content: content,
    });
    const options = {
      hostname: '127.0.0.1',
      port: 27123,
      path: '/vault/',
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${API_KEY}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve({ status: res.statusCode, data }));
    });
    req.on('error', (err) => resolve({ status: 0, error: err.message }));
    req.write(body);
    req.end();
  });
}

/**
 * Formate la date ISO en YYYY-MM-DD HH:MM.
 */
function formatDate() {
  const now = new Date();
  return now.toISOString().replace('T', ' ').substring(0, 16);
}

async function main() {
  try {
    const stamp = formatDate();
    const projectLine = PROJECT_NAME ? ` — [${PROJECT_NAME}]` : '';
    const summaryLine = SUMMARY ? `\n${SUMMARY}` : '';

    // Construire l'entrée LOG
    const logEntry = `\n## ${stamp}${projectLine}${summaryLine}\n\nSession: ${SESSION_ID}\n`;

    // Lire le LOG existant
    const existingLog = await readVaultFile('LOG.md');
    const newLog = existingLog
      ? existingLog.trimEnd() + logEntry
      : `# LOG — Journal de session\n\n${logEntry.trimStart()}`;

    await writeVaultFile('LOG.md', newLog);

    console.log(JSON.stringify({
      metadata: { sessionSaved: stamp, project: PROJECT_NAME }
    }));
  } catch (err) {
    console.log(JSON.stringify({
      metadata: { sessionSaveError: err.message }
    }));
  }
}

main();
