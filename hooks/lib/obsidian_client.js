/**
 * obsidian_client.js — Minimal Obsidian Local REST API client.
 *
 * Shared by session-start-memory and session-end-save, which previously each
 * carried their own copy (and drifted: one honoured OBSIDIAN_API_URL, the
 * other hardcoded host and port).
 *
 * Node.js stdlib only — zero external dependency, identical on every OS.
 *
 * Endpoint resolution, in order:
 *   1. OBSIDIAN_API_URL, when set — used verbatim
 *   2. https://127.0.0.1:27124 — the plugin's DEFAULT (encrypted, self-signed)
 *   3. http://127.0.0.1:27123  — only if the user enabled the non-encrypted
 *                                server, which the plugin ships DISABLED
 *
 * The HTTPS certificate is self-signed by design (it is generated locally by
 * the plugin), so verification is disabled for 127.0.0.1 only. Never point
 * OBSIDIAN_API_URL at a remote host: this client would not authenticate it.
 */

const http = require('http');
const https = require('https');
const { URL } = require('url');

const API_KEY = process.env.OBSIDIAN_API_KEY || '';

const ENDPOINTS = process.env.OBSIDIAN_API_URL
  ? [process.env.OBSIDIAN_API_URL]
  : ['https://127.0.0.1:27124', 'http://127.0.0.1:27123'];

const TIMEOUT_MS = Number(process.env.OBSIDIAN_API_TIMEOUT_MS || 4000);

/** Result of any vault call: `ok` distinguishes "empty file" from "call failed". */
function result(ok, body, error) {
  return { ok, body: body || '', error: error || null };
}

function isLoopback(urlString) {
  try {
    const host = new URL(urlString).hostname;
    return host === '127.0.0.1' || host === 'localhost' || host === '::1';
  } catch {
    return false;
  }
}

function request(base, { method, path, body }) {
  return new Promise((resolve) => {
    let url;
    try {
      url = new URL(path, base);
    } catch (err) {
      resolve(result(false, '', `bad url: ${err.message}`));
      return;
    }

    const secure = url.protocol === 'https:';
    const lib = secure ? https : http;
    const options = {
      method,
      hostname: url.hostname,
      port: url.port || (secure ? 443 : 80),
      path: url.pathname + url.search,
      headers: { Authorization: `Bearer ${API_KEY}` },
      timeout: TIMEOUT_MS,
    };

    // The plugin's certificate is self-signed and local. Accept it for
    // loopback only — never for a remote endpoint.
    if (secure && isLoopback(base)) options.rejectUnauthorized = false;

    if (body !== undefined) {
      options.headers['Content-Type'] = 'text/markdown; charset=utf-8';
      options.headers['Content-Length'] = Buffer.byteLength(body);
    }

    const req = lib.request(options, (res) => {
      let data = '';
      res.on('data', (c) => { data += c; });
      res.on('end', () => {
        const ok = res.statusCode >= 200 && res.statusCode < 300;
        resolve(ok ? result(true, data)
                   : result(false, data, `HTTP ${res.statusCode}`));
      });
    });

    req.on('timeout', () => { req.destroy(); resolve(result(false, '', 'timeout')); });
    req.on('error', (err) => resolve(result(false, '', err.message)));
    if (body !== undefined) req.write(body);
    req.end();
  });
}

/** Try each candidate endpoint until one answers; report the last error. */
async function tryEndpoints(spec) {
  let last = result(false, '', 'no endpoint tried');
  for (const base of ENDPOINTS) {
    const res = await request(base, spec);
    // A 404 is a real answer from a reachable server — do not fall through.
    if (res.ok || (res.error && res.error.startsWith('HTTP'))) return res;
    last = res;
  }
  return last;
}

/**
 * Read a file from the vault.
 * @returns {Promise<{ok: boolean, body: string, error: string|null}>}
 *   `ok:false` means the call failed — NOT that the file is empty. Callers
 *   must never treat a failed read as "the file has no content".
 */
async function readVaultFile(vaultPath) {
  return tryEndpoints({
    method: 'GET',
    path: `/vault/${encodeURI(vaultPath)}`,
  });
}

/** Overwrite a vault file. Returns the same shape as readVaultFile. */
async function writeVaultFile(vaultPath, content) {
  return tryEndpoints({
    method: 'PUT',
    path: `/vault/${encodeURI(vaultPath)}`,
    body: content,
  });
}

/** Append to a vault file — safe under concurrency, no read-modify-write. */
async function appendVaultFile(vaultPath, content) {
  return tryEndpoints({
    method: 'POST',
    path: `/vault/${encodeURI(vaultPath)}`,
    body: content,
  });
}

module.exports = {
  API_KEY,
  ENDPOINTS,
  readVaultFile,
  writeVaultFile,
  appendVaultFile,
  configured: () => API_KEY.length > 0,
};
