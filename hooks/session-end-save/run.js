/**
 * run.js — SessionEnd memory saver.
 *
 * Writes one immutable session note per session and appends a single
 * line to the v4 LOG. Never edits `BOARD.md` (boards are generated
 * and are the authority for status — the contract is "boards are
 * derived, not hand-edited").
 *
 * Node.js stdlib only — zero external dependency.
 *
 * Usage: node run.js
 * Environment:
 *   OBSIDIAN_API_KEY        - Local REST API key (no-op without it)
 *   OBSIDIAN_API_URL        - override endpoint (default: https://127.0.0.1:27124)
 *   OBSIDIAN_VAULT          - vault path, used to infer the default slug
 *   OBSIDIAN_PROJECT_SLUG   - explicit project slug; REQUIRED in v4 layout
 *   SESSION_ID              - session id (used to name the note)
 *   PROJECT_NAME            - project display name (free text, optional)
 *   SESSION_SUMMARY         - summary text (optional)
 *
 * Concurrency model:
 *   - Each session writes its own file under
 *     `projects/<slug>/operations/sessions/<id>.md` via PUT. PUT is
 *     idempotent for a given path, so two sessions racing on the SAME
 *     id is safe; two sessions on DIFFERENT ids are independent and
 *     both notes land.
 *   - The LOG append uses POST. The Obsidian Local REST API
 *     `POST /vault/{path}` is documented as "active append" — it does
 *     not perform a read-modify-write, so concurrent appends do not
 *     truncate each other. If a transport error occurs mid-append, we
 *     never fall back to overwriting: the failure is reported and the
 *     next session can retry by re-running this hook with the same id.
 *
 * v4 layout (only when both OBSIDIAN_VAULT and OBSIDIAN_PROJECT_SLUG
 * are set and the slug matches the v4 grammar):
 *   - Session note: projects/<slug>/operations/sessions/<id>.md
 *   - LOG.md at the vault root (single, append-only)
 *
 * Legacy layout (when OBSIDIAN_PROJECT_SLUG is not set):
 *   - LOG.md at the path OBSIDIAN_LOG_PATH (default: LOG.md)
 *   - No session note; LOG entry carries the full summary.
 */

const path = require('path');
const { appendVaultFile, writeVaultFile, configured } = require(path.join(__dirname, '..', 'lib', 'obsidian_client'));

const SESSION_ID = process.env.SESSION_ID || 'unknown';
const PROJECT_NAME = process.env.PROJECT_NAME || '';
const SUMMARY = process.env.SESSION_SUMMARY || '';
const SLUG = process.env.OBSIDIAN_PROJECT_SLUG || '';
const LOG_PATH = process.env.OBSIDIAN_LOG_PATH || 'LOG.md';

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

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

function frontmatter(stamp, slug) {
  // v4 contract: schema_version 4, project = slug, type = log.
  // Quoting slug avoids YAML surprises if it ever needs escaping.
  return [
    '---',
    'schema_version: 4',
    `project: "${slug}"`,
    'type: log',
    'tags: [session, generated]',
    `created: ${stamp.replace(' ', 'T')}`,
    'related: [["projects/' + slug + '/BOARD"]], [["projects/' + slug + '/AGENTS"]]',
    '---',
    '',
  ].join('\n');
}

function buildNote(stamp, slug, projectName, summary, sessionId) {
  const lines = [
    frontmatter(stamp, slug),
    `# Session ${sessionId} — ${stamp}`,
    '',
  ];
  if (projectName) lines.push(`- Project: ${projectName}`);
  if (slug)       lines.push(`- Slug: ${slug}`);
  if (summary) {
    lines.push('', '## Summary', '', summary);
  }
  return lines.join('\n') + '\n';
}

function buildLogEntry(stamp, slug, projectName, summary, sessionId) {
  const projectLine = projectName || slug ? ` — [${projectName || slug}]` : '';
  const summaryLine = summary ? `\n${summary.replace(/\n/g, ' ').slice(0, 200)}` : '';
  return `\n## ${stamp}${projectLine}${summaryLine}\n\nSession: ${sessionId} | slug: ${slug || '(none)'}\n`;
}

async function main() {
  if (!configured()) {
    emit({ sessionSaveSkipped: 'OBSIDIAN_API_KEY not set' });
    return;
  }

  // When the slug is set, validate it before doing anything. A bad slug
  // would otherwise create a project directory the validator doesn't
  // know about, and the next sync would have to either silently accept
  // it or refuse to commit.
  const slugValid = SLUG === '' || SLUG_RE.test(SLUG);

  const stamp = formatStamp();

  // v4 path: one immutable note per session, plus a one-line LOG append.
  // Legacy path: just the LOG entry.
  let noteResult = { ok: true, skipped: true };
  if (SLUG) {
    if (!slugValid) {
      emit({
        sessionSaveError: `OBSIDIAN_PROJECT_SLUG=${JSON.stringify(SLUG)} does not match v4 grammar`,
        needsTriage: true,
      });
      return;
    }
    const notePath = `projects/${SLUG}/operations/sessions/${SESSION_ID}.md`;
    const note = buildNote(stamp, SLUG, PROJECT_NAME, SUMMARY, SESSION_ID);
    noteResult = await writeVaultFile(notePath, note);
    if (!noteResult.ok) {
      emit({
        sessionSaveError: noteResult.error,
        notePath,
        needsTriage: true,
      });
      return;
    }
  }

  const entry = buildLogEntry(stamp, SLUG, PROJECT_NAME, SUMMARY, SESSION_ID);
  const logResult = await appendVaultFile(LOG_PATH, entry);

  if (!logResult.ok) {
    // Report the failure; never fall back to overwriting the log.
    // The session note (if any) is left in place — the operator can
    // manually dedupe by id if the LOG append ever needs replaying.
    emit({
      sessionSaveError: logResult.error,
      logPath: LOG_PATH,
      noteWritten: noteResult.ok && !noteResult.skipped ? `projects/${SLUG}/operations/sessions/${SESSION_ID}.md` : null,
    });
    return;
  }

  emit({
    sessionSaved: stamp,
    project: PROJECT_NAME || SLUG || null,
    slug: SLUG || null,
    logPath: LOG_PATH,
    notePath: SLUG ? `projects/${SLUG}/operations/sessions/${SESSION_ID}.md` : null,
    layout: SLUG ? 'v4' : 'legacy',
  });
}

main().catch((err) => emit({ sessionSaveError: err.message }));
