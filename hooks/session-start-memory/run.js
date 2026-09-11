/**
 * run.js — SessionStart memory loader.
 *
 * Loads session context from the Obsidian vault via the Local REST API.
 * Node.js stdlib only — zero external dependency.
 *
 * Usage: node run.js
 * Environment:
 *   OBSIDIAN_API_KEY       - Local REST API key (required for vault access; no-op without it)
 *   OBSIDIAN_API_URL       - override endpoint (default: https://127.0.0.1:27124)
 *   OBSIDIAN_VAULT         - vault path, used to resolve legacy paths and pick a default slug
 *   OBSIDIAN_PROJECT_SLUG  - explicit project slug; overrides any inference
 *
 * Emits JSON on stdout: { metadata: { sessionContext: {...} } }
 *
 * Distinguishes three failure modes the caller has to react to
 * differently, instead of folding them all into "loaded, but empty":
 *
 *   loaded: false, error: <transport>          — vault unreachable, API down
 *   loaded: false, missing: [<path>, ...]      — vault reachable, files absent
 *   loaded: false, missing: []                 — file present but empty / OK path
 *
 * The v4 layout lives in `projects/<slug>/AGENTS.md` and
 * `projects/<slug>/BOARD.md`. Legacy `_global/handoff.md` and
 * `memory/user.md` are still honoured when `OBSIDIAN_VAULT` points at an
 * older vault, so a user who hasn't migrated yet is not locked out —
 * but the response carries a `layout` field so the harness knows which
 * generation it's looking at.
 */

const path = require('path');
const { createObsidianClient, governedObsidianConfiguration } = require(path.join(__dirname, '..', 'lib', 'obsidian_client'));
const { RuntimeAuthority } = require(path.join(__dirname, '..', 'lib', 'runtime_authority'));

const CALLER_IDENTITY = 'session-start-memory';

const USER_MEMORY_PATH = process.env.OBSIDIAN_USER_MEMORY_PATH || 'memory/user.md';
const HANDOFF_PATH = process.env.OBSIDIAN_HANDOFF_PATH || '_global/handoff.md';

const V4_PROJECT_AGENTS = (slug) => `projects/${slug}/AGENTS.md`;
const V4_PROJECT_BOARD = (slug) => `projects/${slug}/BOARD.md`;
const V4_PROJECT_INDEX = (slug) => `projects/${slug}/INDEX.md`;
const V4_ROOT_AGENTS = 'AGENTS.md';

/** Keep the first `maxLines` non-blank lines of a markdown file. */
function extractSummary(content, maxLines) {
  if (!content) return '';
  return content.split('\n').filter((l) => l.trim()).slice(0, maxLines).join('\n');
}

/** Trim a leading BOM and CR characters that the API sometimes ships. */
function normalize(body) {
  if (!body) return '';
  if (body.charCodeAt(0) === 0xfeff) body = body.slice(1);
  return body.replace(/\r\n/g, '\n');
}

function resolveSlug() {
  const explicit = process.env.OBSIDIAN_PROJECT_SLUG;
  if (explicit && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(explicit)) return explicit;
  return null;
}

function emit(sessionContext) {
  console.log(JSON.stringify({ metadata: { sessionContext } }));
}

/**
 * Build the authority from process.env. This is the one place in this file
 * allowed to read security-critical environment variables — everything
 * below `main()` receives only a RuntimeContextHandle and must resolve it
 * through `authority` as CALLER_IDENTITY to reach the actual credential.
 */
function buildAuthorityFromEnv() {
  return new RuntimeAuthority(process.env.MULTIVAULT_SECURITY_DOMAIN_ID, {
    apiKey: governedObsidianConfiguration().apiKey,
    endpoints: governedObsidianConfiguration().endpoints,
    timeoutMs: Number(process.env.OBSIDIAN_API_TIMEOUT_MS),
  });
}

async function loadSessionContext(authority, handle) {
  // A denied resolution (foreign handle, wrong caller, revoked) degrades to
  // the same "unconfigured" state createObsidianClient already treats as a
  // clean skip — never a different code path, never a leak.
  const state = authority.resolve(handle, CALLER_IDENTITY) || {};
  const client = createObsidianClient({
    securityDomainId: state.securityDomainId,
    apiKey: state.apiKey,
    endpoints: state.endpoints,
    timeoutMs: state.timeoutMs,
  });
  const slug = resolveSlug();
  const wantV4 = Boolean(slug);
  if (!client.configured()) {
    const keyMissing = client.configurationError === 'OBSIDIAN_API_KEY not set';
    emit(keyMissing
      ? { loaded: false, skipped: client.configurationError }
      : { loaded: false, error: client.configurationError, needsTriage: true, layout: wantV4 ? 'v4' : 'legacy' });
    return;
  }

  // v4 paths are tried first; the legacy ones stay as a safety net.
  const candidates = [];
  if (wantV4) {
    candidates.push({ name: 'projectAgents', path: V4_PROJECT_AGENTS(slug) });
    candidates.push({ name: 'projectBoard',  path: V4_PROJECT_BOARD(slug) });
    candidates.push({ name: 'projectIndex',  path: V4_PROJECT_INDEX(slug) });
    candidates.push({ name: 'rootAgents',    path: V4_ROOT_AGENTS });
  }
  candidates.push({ name: 'userMemory', path: USER_MEMORY_PATH });
  candidates.push({ name: 'handoff',    path: HANDOFF_PATH });

  const results = await Promise.all(candidates.map(async (c) => {
    const r = await client.readVaultFile(c.path);
    return { ...c, ...r, body: normalize(r.body) };
  }));

  // Reduce: a single HTTP error (vault unreachable) overrides everything
  // and is reported as such; per-file `missing` is a different state.
  const anyHttpError = results.some((r) => r.error && r.error.startsWith('HTTP'));
  const allTransportFailed = results.length > 0 && results.every((r) => !r.ok && r.error && !r.error.startsWith('HTTP'));

  if (anyHttpError || allTransportFailed) {
    emit({
      loaded: false,
      error: results.map((r) => r.error).filter(Boolean)[0] || 'vault unreachable',
      triedEndpoints: client.endpoints,
      layout: wantV4 ? 'v4' : 'legacy',
    });
    return;
  }

  const present = results.filter((r) => r.ok && r.body);
  const missing = results.filter((r) => !r.ok).map((r) => r.path);
  const empty = results.filter((r) => r.ok && !r.body).map((r) => r.path);

  if (present.length === 0) {
    // Vault reachable, but every file we tried is absent. This is a
    // needs-triage signal, not a transport error — and the harness
    // should react differently (e.g. prompt for a slug).
    emit({
      loaded: false,
      missing,
      empty,
      needsTriage: true,
      layout: wantV4 ? 'v4' : 'legacy',
      hint: wantV4
        ? `no notes found for slug '${slug}' under projects/${slug}/`
        : 'no notes found and OBSIDIAN_PROJECT_SLUG is not set',
    });
    return;
  }

  const byName = Object.fromEntries(present.map((r) => [r.name, r.body]));

  emit({
    loaded: true,
    layout: wantV4 ? 'v4' : 'legacy',
    slug: slug || null,
    userMemory: extractSummary(byName.userMemory, 30),
    handoff: extractSummary(byName.handoff, 30),
    v4: wantV4 ? {
      projectAgents: extractSummary(byName.projectAgents, 30),
      projectBoard:  extractSummary(byName.projectBoard, 30),
      projectIndex:  extractSummary(byName.projectIndex, 30),
      rootAgents:    extractSummary(byName.rootAgents, 30),
    } : null,
    missing,
    empty,
  });
}

async function main() {
  const authority = buildAuthorityFromEnv();
  const handle = authority.issueHandle(CALLER_IDENTITY);
  await loadSessionContext(authority, handle);
}

main().catch((err) => emit({ loaded: false, error: err.message }));
