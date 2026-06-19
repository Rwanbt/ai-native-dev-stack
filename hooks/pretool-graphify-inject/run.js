/**
 * pretool-graphify-inject.js — PreToolUse graphify inject
 *
 * Lit la commande Bash entrante. Si elle contient grep/rg/find/ack/ag
 * ET que graphify-out/graph.json existe dans le cwd, injecte le contexte.
 *
 * Compatible: Claude Code, Codex, MiniMax Code, Aider (via prompt system).
 * Node.js stdlib uniquement.
 *
 * Usage: node run.js
 * stdin: payload JSON de l'agent avec tool_input.command
 * stdout: JSON { hookSpecificOutput: ... } ou vide (silence = pas d'injection)
 */

const fs = require('fs');
const path = require('path');

const SEARCH_TOOLS = ['grep', 'rg', 'ripgrep', 'find', 'fd', 'ack', 'ag'];

function readStdin() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => data += chunk);
    process.stdin.on('end', () => resolve(data));
  });
}

async function main() {
  let payload;
  try {
    const raw = await readStdin();
    payload = JSON.parse(raw);
  } catch {
    return;
  }

  const command = (payload.tool_input || payload.input?.tool_input || {}).command || '';
  const cwd = payload.cwd || process.cwd();

  const lower = command.toLowerCase();
  const isSearch = SEARCH_TOOLS.some(tool => {
    const re = new RegExp(`(^|\\s|\\b)${tool}(\\s|$)`);
    return re.test(lower);
  });
  if (!isSearch) return;

  const graphPath = path.join(cwd, 'graphify-out', 'graph.json');
  if (!fs.existsSync(graphPath)) return;

  const message = 'graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files.';
  console.log(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: message,
    },
  }));
}

main();
