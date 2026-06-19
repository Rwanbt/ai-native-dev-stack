/**
 * session-start-memory.js — SessionStart Memory Loader
 *
 * Charge le contexte de session depuis le vault Obsidian local.
 * Node.js stdlib uniquement — zéro dépendance externe.
 *
 * Usage: node run.js
 * Retourne JSON sur stdout: { userMemory, handoff, lastSession }
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

// Obsidian Local REST API key — read from the environment, never hardcoded.
// Set OBSIDIAN_API_KEY in your shell/agent config (see README.md).
const API_KEY = process.env.OBSIDIAN_API_KEY || '';
const VAULT_BASE = process.env.OBSIDIAN_API_URL || 'http://127.0.0.1:27123';

/**
 * Lit un fichier du vault Obsidian via l'API REST locale.
 * @param {string} vaultPath - Chemin relatif dans le vault (ex: "_global/handoff.md")
 * @returns {Promise<string>} Contenu du fichier ou chaîne vide
 */
async function readVaultFile(vaultPath) {
  return new Promise((resolve) => {
    const url = `${VAULT_BASE}/vault/?path=${encodeURIComponent(vaultPath)}`;
    const options = {
      headers: { 'Authorization': `Bearer ${API_KEY}` },
    };
    http.get(url, options, (res) => {
      if (res.statusCode !== 200) {
        resolve('');
        return;
      }
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
      res.on('error', () => resolve(''));
    }).on('error', () => resolve(''));
  });
}

/**
 * Extrait un résumé depuis un fichier markdown (N premières lignes).
 * @param {string} content
 * @param {number} maxLines
 */
function extractSummary(content, maxLines = 20) {
  if (!content) return '(aucun contenu)';
  const lines = content.split('\n').filter(l => l.trim());
  return lines.slice(0, maxLines).join('\n');
}

async function main() {
  try {
    const [userMemory, handoff] = await Promise.all([
      readVaultFile('memory/user.md'),
      readVaultFile('_global/handoff.md'),
    ]);

    const result = {
      userMemory: extractSummary(userMemory, 30),
      handoff: extractSummary(handoff, 30),
      loaded: !!(userMemory || handoff),
    };

    console.log(JSON.stringify({ metadata: { sessionContext: result } }));
  } catch (err) {
    console.log(JSON.stringify({ metadata: { sessionContext: { error: err.message } } }));
  }
}

main();
