/** Domain-scoped Obsidian Local REST client.
 *
 * This module deliberately reads no process environment. A caller constructs one
 * client with its domain identity, credential and approved loopback endpoint(s).
 * It is a GUARDED boundary only until MV-09 can supply live vault correlation.
 */

const http = require('http');
const https = require('https');
const { URL } = require('url');

const DEFAULT_ENDPOINTS = Object.freeze([
  'https://127.0.0.1:27124',
  'http://127.0.0.1:27123',
]);
const DEFAULT_TIMEOUT_MS = 4000;
const LITERAL_LOOPBACK_HOSTS = new Set(['127.0.0.1', '::1']);

function result(ok, body, error) {
  return { ok, body: body || '', error: error || null };
}

function normalizeEndpoint(value) {
  try {
    const endpoint = new URL(value);
    if (!['http:', 'https:'].includes(endpoint.protocol)
      || !LITERAL_LOOPBACK_HOSTS.has(endpoint.hostname)
      || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
      return null;
    }
    return endpoint.toString().replace(/\/$/, '');
  } catch {
    return null;
  }
}

function normalizeEndpoints(values) {
  if (!Array.isArray(values) || values.length === 0) return null;
  const endpoints = values.map(normalizeEndpoint);
  return endpoints.every(Boolean) ? endpoints : null;
}

function request(base, apiKey, timeoutMs, { method, path, body }) {
  return new Promise((resolve) => {
    let url;
    try {
      url = new URL(path, base);
    } catch (error) {
      resolve(result(false, '', `bad url: ${error.message}`));
      return;
    }
    const secure = url.protocol === 'https:';
    const options = {
      method,
      hostname: url.hostname,
      port: url.port || (secure ? 443 : 80),
      path: url.pathname + url.search,
      headers: { Authorization: `Bearer ${apiKey}` },
      timeout: timeoutMs,
    };
    // The only accepted HTTPS endpoints are literal local loopback addresses.
    if (secure) options.rejectUnauthorized = false;
    if (body !== undefined) {
      options.headers['Content-Type'] = 'text/markdown; charset=utf-8';
      options.headers['Content-Length'] = Buffer.byteLength(body);
    }
    const transport = secure ? https : http;
    const requestHandle = transport.request(options, (response) => {
      let data = '';
      response.on('data', (chunk) => { data += chunk; });
      response.on('end', () => {
        const ok = response.statusCode >= 200 && response.statusCode < 300;
        resolve(ok ? result(true, data) : result(false, data, `HTTP ${response.statusCode}`));
      });
    });
    requestHandle.on('timeout', () => {
      requestHandle.destroy();
      resolve(result(false, '', 'timeout'));
    });
    requestHandle.on('error', (error) => resolve(result(false, '', error.message)));
    if (body !== undefined) requestHandle.write(body);
    requestHandle.end();
  });
}

function governedObsidianConfiguration(env = process.env) {
  // Ambient credentials are refused unless the governed launcher set the marker.
  const governed = env.AINATIVE_MULTIVAULT_GOVERNED === '1';
  return {
    governed,
    apiKey: governed && typeof env.OBSIDIAN_API_KEY === 'string' ? env.OBSIDIAN_API_KEY : '',
    endpoints: governed && env.OBSIDIAN_API_URL ? [env.OBSIDIAN_API_URL] : undefined,
  };
}

function createObsidianClient({ securityDomainId, apiKey, endpoints, timeoutMs } = {}) {
  const normalizedEndpoints = normalizeEndpoints(endpoints || DEFAULT_ENDPOINTS);
  const domain = typeof securityDomainId === 'string' ? securityDomainId.trim() : '';
  const key = typeof apiKey === 'string' ? apiKey : '';
  const timeout = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS;
  const configurationError = !key
    ? 'OBSIDIAN_API_KEY not set'
    : !domain
      ? 'MULTIVAULT_SECURITY_DOMAIN_ID not set'
      : !normalizedEndpoints
        ? 'invalid domain-scoped Obsidian endpoint configuration'
        : null;

  async function tryEndpoints(spec) {
    let last = result(false, '', 'no endpoint tried');
    for (const endpoint of normalizedEndpoints || []) {
      const response = await request(endpoint, key, timeout, spec);
      if (response.ok || (response.error && response.error.startsWith('HTTP'))) return response;
      last = response;
    }
    return last;
  }

  return Object.freeze({
    securityDomainId: domain,
    endpoints: Object.freeze(normalizedEndpoints || []),
    configured: () => configurationError === null,
    configurationError,
    readVaultFile: (vaultPath) => tryEndpoints({ method: 'GET', path: `/vault/${encodeURI(vaultPath)}` }),
    writeVaultFile: (vaultPath, content) => tryEndpoints({ method: 'PUT', path: `/vault/${encodeURI(vaultPath)}`, body: content }),
    appendVaultFile: (vaultPath, content) => tryEndpoints({ method: 'POST', path: `/vault/${encodeURI(vaultPath)}`, body: content }),
  });
}

module.exports = { DEFAULT_ENDPOINTS, createObsidianClient, governedObsidianConfiguration };
