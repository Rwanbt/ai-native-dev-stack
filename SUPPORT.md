# Support

## What is supported

| Surface | Supported |
|---|---|
| Installation | The pinned GitHub release tag (current), or a checkout + `install.py`. PyPI is wired and gated but not yet published: it needs a one-time Trusted Publisher setup on the PyPI account (`docs/RELEASING.md`). |
| Python | 3.11+ for the lifecycle CLI; the AI-docs tooling installed into a project runs on 3.8+ |
| Operating systems | Linux, macOS and Windows (CI exercises all three) |
| Profiles | Standard; Verified (adds governed Work Contracts and deterministic verification) |
| Harnesses | Claude Code, Codex, OpenCode, Cursor, Gemini CLI, MiniMax/Mavis — for the shared method, skills and hooks |
| Work management | Generic Git; GitHub (mapping); GitLab (mapping). The Work Authority is resolved locally, purely and fail-closed (ADR-0018) |
| Features | Project-scope features independent of the profile (`forge-github` default, `forge-gitlab`), State schema V2 (ADR-0017) |
| Release sources | GitHub.com (built-in, qualified); a local mirror; an anonymous HTTPS release API (`AINATIVE_UPDATE_URL`, never credentialed); GitLab.com (qualified live: Generic Package Registry anchor, managed releases, exact version chain — 2026-09-16); GitLab Self-Managed and GitHub Enterprise Server UNTESTED — **not supported** |

Only the latest release is supported; fixes ship as a new patch version.

## Before asking for help

1. `ainative doctor` — prints the lifecycle health, the Knowledge status and
   the environment (Git, Python, the harness hook, optional tools, the vault
   when configured). Its output is the first thing any bug report needs.
2. `ainative status` — what is installed and its health.
3. `ainative update check` — whether a newer release exists, and whether the
   CLI must be upgraded first (`CLI_UPDATE_REQUIRED`).
4. The guides: `docs/DISTRIBUTION-LIFECYCLE.md`, `docs/VERIFIED-WORK-PLANE.md`,
   `docs/knowledge/KNOWLEDGE-CONVERGENCE-MATRIX.md`, `docs/MULTIVAULT-OPERATOR-GUIDE.md`,
   `UPDATING.md`.

## Reporting a bug

Open a GitHub issue with **exactly this**, and nothing else:

```
ainative --version            # version(s)
OS:                           # e.g. Windows 11, Ubuntu 24.04, macOS 15
Python:                       # e.g. 3.11.9
ainative doctor --json        # paste the JSON (redact paths that contain your name)
the exact command you ran
its output, with any token or credential replaced by <redacted>
```

For a machine-wide install, add `ainative machine status --json`; for a project,
the command and output above are enough.

Do **not** include secrets, tokens, credentials, personal file contents or the
contents of `~/.claude/`, your vault, or `.ai-native/` directories beyond what
the command printed. Redact paths if they contain your name.

Security issues follow `SECURITY.md` — a private report, never a public issue.

## Expected response

This is a single-maintainer project: there is no response-time SLA and none is
promised. Reports are triaged against the reproduced facts; a confirmed
security or data-loss defect takes precedence over features.

## Known limitations (honest list)

- Runtimes older than v2.2.2 cannot consume protocol v2 releases; upgrade the
  CLI first (README, UPDATING.md).
- `SHA256SUMS` proves integrity, not a human signature; releases carry GitHub
  build-provenance attestations, and #24 tracks stronger signing.
- Multi-Vault is **GUARDED**, not ENFORCED: it does not claim protection from a
  malicious process running as the same OS user outside governed paths.
- Knowledge canonical auto-promotion is intentionally not shipped (K5 = STOP).
- Machine-wide integration is repaired from what the manifest records: a
  schema-1 manifest (written by releases before v2.4.0) repairs links, and
  reports blocks and rendered files as unrepairable rather than guessing.
- Workspace/global multi-user machine ACL isolation is not claimed or tested.