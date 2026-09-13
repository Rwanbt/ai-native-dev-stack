# Support

## What is supported

| Surface | Supported |
|---|---|
| Installation | PyPI (`pip install ainative-dev-stack==<version>`), pinned git tag, or a checkout + `install.py` |
| Python | 3.11+ for the lifecycle CLI; the AI-docs tooling installed into a project runs on 3.8+ |
| Operating systems | Linux, macOS and Windows (CI exercises all three) |
| Profiles | Standard; Verified (adds governed Work Contracts and deterministic verification) |
| Harnesses | Claude Code, Codex, OpenCode, Cursor, Gemini CLI, MiniMax/Mavis — for the shared method, skills and hooks |

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

Open a GitHub issue with:

- the exact command you ran and its output (`ainative doctor --json` if the
  command involves the lifecycle);
- your OS, Python version and the installed stack version
  (`ainative --version`);
- what you expected and what happened.

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
- Workspace/global multi-user machine ACL isolation is not claimed or tested.