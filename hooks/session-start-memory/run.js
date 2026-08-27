/**
 * run.js — SessionStart memory loader.
 *
 * Loads session context from the Obsidian vault via the Local REST API.
 * Node.js stdlib only — zero external dependency.
 *
 * Usage: node run.js
 * Environment:
 *   OBSIDIAN_API_KEY  - Local REST API key (required; without it, no-op)
 *   OBSIDIAN_API_URL  - override endpoint (default: https://127.0.0.1:27124)
 *
 * Emits JSON on stdout: { metadata: { sessionContext: {...} } }
 *
 * A failed read is reported as such — it is never silently reported as
 * "loaded, but empty", which is what made a misconfigured endpoint look like
 * a working hook.
 */

const path = require('path');
const { readVaultFile, configured, ENDPOINTS } = require(path.join(__dirname, '..', 'lib', 'obsidian_client'));

const USER_MEMORY_PATH = process.env.OBSIDIAN_USER_MEMORY_PATH || 'memory/user.md';
const HANDOFF_PATH = process.env.OBSIDIAN_HANDOFF_PATH || '_global/handoff.md';

/** Keep the first `maxLines` non-blank lines of a markdown file. */
function extractSummary(content, maxLines) {
  if (!content) return '';
  return content.split('\n').filter((l) => l.trim()).slice(0, maxLines).join('\n');
}

function emit(sessionContext) {
  console.log(JSON.stringify({ metadata: { sessionContext } }));
}

async function main() {
  if (!configured()) {
    emit({ loaded: false, skipped: 'OBSIDIAN_API_KEY not set' });
    return;
  }

  const [userMemory, handoff] = await Promise.all([
    readVaultFile(USER_MEMORY_PATH),
    readVaultFile(HANDOFF_PATH),
  ]);

  // Distinguish "unreachable vault" from "vault reachable, notes absent".
  if (!userMemory.ok && !handoff.ok) {
    emit({
      loaded: false,
      error: userMemory.error || handoff.error,
      triedEndpoints: ENDPOINTS,
    });
    return;
  }

  emit({
    userMemory: extractSummary(userMemory.body, 30),
    handoff: extractSummary(handoff.body, 30),
    loaded: Boolean(userMemory.body || handoff.body),
    missing: [
      userMemory.ok ? null : USER_MEMORY_PATH,
      handoff.ok ? null : HANDOFF_PATH,
    ].filter(Boolean),
  });
}

main().catch((err) => emit({ loaded: false, error: err.message }));
