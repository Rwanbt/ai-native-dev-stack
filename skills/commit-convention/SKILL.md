---
name: commit-convention
description: |
  Conventional Commits 1.0 enforcer. Two complementary modes:

  (1) AUTO-SUGGEST — when you say "commit", "commit my changes", "commit this",
      or invoke `/commit`, the skill inspects `git diff --staged`, proposes 1–3
      conventional commit messages (type + optional scope + subject), and asks
      which one to use. You never have to remember the format.

  (2) VALIDATOR — every `git commit` passes through a PreToolUse hook that
      validates the first line of the message against the Conventional Commits
      regex. Non-conformant commits trigger a confirm prompt — they cannot
      slip through silently.

  Types allowed: feat, fix, refactor, perf, docs, test, chore, build, ci,
  style, revert. Optional scope in parentheses (lowercase kebab-case, ≤ 20
  chars). Optional `!` and `BREAKING CHANGE:` footer.

  Use when: "commit", "commit my changes", "make a commit", "commit this",
  "validate commit", "/commit".
  Proactively invoke whenever the user says "commit" or runs `git commit`
  through the agent, and after a logical unit of work is staged and idle.
  Mirrors the format already enforced by the AI-Native-Dev-Stack itself
  (see CONTRIBUTING.md and AGENTS.md → "Git & collaboration").
origin: generic
---

# /commit-convention — Conventional Commits 1.0 enforcer

Two complementary behaviors. Apply both — the user must be protected from
non-conformant commits in every code path.

---

## Mode 1 — Auto-suggest (primary entry point)

Invoke when the user says any of: "commit", "commit my changes",
"commit this", "commit everything", "make a commit", `/commit`, or when a
non-empty staged diff is idle and the user seems ready to commit.

### Step 1 — Read the staged diff

```bash
git rev-parse --is-inside-work-tree 2>/dev/null || { echo "NOT_A_GIT_REPO"; exit 0; }

git diff --cached --stat | head -20
echo "---"
git diff --cached --shortstat
```

If nothing is staged, warn and fall back to unstaged:

```bash
echo "Nothing staged — falling back to unstaged changes."
git diff --stat | head -20
```

If still empty → "Nothing to commit, working tree clean." Stop.

### Step 2 — Infer type, scope, subject

Apply heuristics IN ORDER. First match wins; if none, ask the user.

**Type inference**

| Signal in the diff                                                       | Type        |
|-------------------------------------------------------------------------|-------------|
| New files in `tests/`, `*_test.*`, `*.test.*`, `spec/`                   | `test`      |
| Only `.md` / docs / `CHANGELOG.md` changes                              | `docs`      |
| Only whitespace / formatting / lint fixes (no logic change)             | `style`     |
| `.github/`, `.gitlab-ci.yml`, `Jenkinsfile`, CI Makefile targets        | `ci`        |
| `Cargo.toml` deps, `package.json` deps, `pyproject.toml`, `Dockerfile` (no logic) | `build` |
| Build tooling configs (`vite.config.*`, `tsconfig.*`, `Makefile`)       | `build`     |
| Pure rename / extract / move with no behavior change                    | `refactor`  |
| New public symbol/route/endpoint, additive change                       | `feat`      |
| Bug fix — words "fix"/"bug"/"crash"/"regression" in message or hunks     | `fix`       |
| Performance — "perf"/"cache"/"memoize" or benchmark-driven              | `perf`      |
| Everything else (cleanup, housekeeping, no semantic change)             | `chore`     |

**Scope inference**

Derive from the *single most prominent directory* of changed files (common
parent). If the diff spans multiple unrelated scopes, leave scope empty.
Limit scope to ≤ 20 chars, lowercase, kebab-case if multi-word.

Examples: `feat(auth): …`, `fix(dsp-eq): …`, `docs(readme): …`,
`chore(deps): …`, `refactor(audio-thread): …`.

**Subject generation**

- Length: **subject ≤ 72 chars** (the part after the colon),
  **full first line ≤ 100 chars** (GitHub UI truncation point).
- Imperative mood ("add" not "added"; "fix" not "fixed").
- Lowercase after the colon.
- **No trailing period.**
- Completes the sentence "If applied, this commit will ___".

### Step 3 — Propose with AskUserQuestion

Surface 1–3 candidates, best-first.

```
Question: "Pick a commit message (or write your own)"
Options:
  1. <type>(<scope>): <subject>      ← best guess
  2. <type>: <subject without scope> ← if scope was ambiguous
  3. chore: <subject>                ← safe fallback
```

The "Type your own answer" option is auto-added.

### Step 4 — Execute (with confirmation)

Always confirm before running `git commit`. Build the command:

- Single-line, ≤ 200 chars → `git commit -m "<M>"`
- Multi-line (body or footer) → use `-m` per paragraph or `-F <tmpfile>`

```bash
MSG_FILE=$(mktemp)
cat > "$MSG_FILE" <<'EOF'
<subject>

<body>

<footer>
EOF
git commit -F "$MSG_FILE"
rm -f "$MSG_FILE"
```

---

## Mode 2 — Validator (PreToolUse hook)

Runs **automatically** before every `git commit` — whether invoked by the
agent, typed through the agent, or any other path. The agent cannot bypass
the *ask*, only the user can.

### Behavior

| Input                                | Result                                  |
|--------------------------------------|-----------------------------------------|
| First line matches CC regex AND no soft warnings | PASS (silent `allow`)         |
| First line matches CC regex BUT full line > 100 chars | ASK with `[warn]` prefix     |
| First line matches CC regex BUT BREAKING CHANGE footer without `!` | ASK with `[warn]` |
| First line does not match            | ASK with violation list                 |
| `--no-verify` present                | PASS (user override)                    |
| No message extractable               | ASK with "no commit message found"      |

### Validator regex (POSIX extended)

```
^(feat|fix|refactor|perf|docs|test|chore|build|ci|style|revert)(\([a-z0-9-]{1,20}\))?!?: .{1,72}$
```

Only the **first line** of the message is checked. Body and footer are
allowed but not line-validated.

### Length rules

- **Subject** (after the colon): ≤ 72 chars — enforced by the regex.
- **Full first line**: ≤ 100 chars — soft warning (ASK) because GitHub UI
  truncates at 100.
- **Trailing period** on first line: ASK with hint.

### Hook wiring (Claude Code)

`.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash <STACK_ROOT>/skills/commit-convention/bin/validate-commit.sh"
          }
        ]
      }
    ]
  }
}
```

`<STACK_ROOT>` resolves to the stack clone root on the machine (for example `~/dev/ai-native-dev-stack/`).
The hook ships with the stack installer (`install.sh` step 2). Other agents
(Codex, OpenCode, MiniMax/Mavis) use the same `bin/validate-commit.sh` —
see each agent's hook docs for the equivalent event name (`pre_tool_use` etc.).

### Source layout

```
skills/commit-convention/
├── SKILL.md                        ← this file
├── bin/
│   ├── validate-commit.sh          ← the hook (called by PreToolUse)
│   └── extract_commit_msg.py       ← message extractor (called by the hook)
└── tests/
    └── test_validate.sh            ← 18 zero-dep smoke tests, all green
```

---

## Format reference (canonical)

### Allowed types

| Type       | When                                                            |
|------------|-----------------------------------------------------------------|
| `feat`     | New user-visible feature                                        |
| `fix`      | Bug fix                                                         |
| `refactor` | Code change that neither fixes a bug nor adds a feature         |
| `perf`     | Performance improvement                                         |
| `docs`     | Documentation only                                              |
| `test`     | Adding or correcting tests                                      |
| `chore`    | Build, deps, tooling, housekeeping (no source change)           |
| `build`    | Build system or external dependencies                           |
| `ci`       | CI configuration files and scripts                              |
| `style`    | Formatting, whitespace, semicolons (no logic change)            |
| `revert`   | Reverts a previous commit (`revert: feat(...): ...`)            |

### Anatomy

```
<type>[(<scope>)][!]: <subject>
<BLANK LINE>
<body>  (optional — wrap at 100 cols)
<BLANK LINE>
<footer>  (optional)
```

### Breaking changes

Either `feat(api)!: drop v1 endpoints` OR a footer line
`BREAKING CHANGE: <description>`. Both is fine.

### Revert

```
revert: feat(auth): add OAuth login

This reverts commit abc123def.
```

---

## Examples

✅ Good
```
feat(auth): add OAuth2 login flow
fix(dsp-eq): prevent denormal flush on idle
refactor(audio-thread): extract ring buffer
perf(renderer): cache glyph atlas between frames
docs(readme): document --release-plugins build flag
test(seno-materia): cover ADSR release edge cases
chore(deps): bump clap-host to 0.4.2
build(workspace): enable LTO on release profile
ci(github): cache cargo registry between runs
style(egui): run rustfmt on gui module
revert: feat(auth): add OAuth2 login flow
feat(api)!: drop v1 endpoints, migrate to v2
```

❌ Bad (validator rejects)
```
Added new feature                                # no type prefix
FEAT(auth): add oauth                            # uppercase type
feat: Add OAuth.                                 # trailing period (warn)
feat(authentication layer): add oauth            # scope has spaces
feat(auth): add oauth login flow with remember me # > 72 chars subject
fixed the bug in the eq                          # not a valid type
```

---

## Boundaries

- Never auto-commit. Always confirm with the user before `git commit`.
- Never rewrite history (`git commit --amend` only on explicit request).
- Never force-push or rebase shared branches.
- Never push to remote unless explicitly asked.
- If the diff is huge (>100 files), surface scope as "unknown" — don't guess.