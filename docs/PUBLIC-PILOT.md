# Public pilot — tomorrow's colleague test, as an executable document

This is the test to hand to a colleague. It takes 20–30 minutes and needs only
Python 3.11+, Git and a network connection. Everything printed below is a
command to run; nothing needs the repository, and no step is hidden.

The pilot has two halves. **Standard** is the baseline every colleague should
pass. **Verified** is optional and takes ten more minutes. Record the answers
in the feedback form at the end — including the failures.

## Prerequisites

- Python 3.11+ (`python --version`)
- Git (`git --version`)
- A network connection (the install and `ainative update check` use it)
- An AI harness is *not required* for the test; if you use Claude Code, the
  PostToolUse hook will be exercised for real (step 6).

## Install

```bash
python -m venv pilot-venv
# Linux / macOS:
source pilot-venv/bin/activate
# Windows (PowerShell):
pilot-venv\Scripts\Activate.ps1

pip install "git+https://github.com/Rwanbt/ai-native-dev-stack.git@v2.4.0"
ainative --version
```

The last command prints the lifecycle version, the state schema and the stack
version. **Pass:** it prints them without an error. Note the versions in the
feedback form.

PyPI (`pip install ainative-dev-stack==2.4.0`) is not published yet — the
one-time trusted-publisher setup on the PyPI account is still pending. The
pinned release above is the supported install for this pilot.

## Standard scenario (15–20 min)

```bash
# 1. A fresh project (any language; Python is only an example).
mkdir pilot-project && cd pilot-project
git init -q .
printf 'def greet(name):\n    return f"hello {name}"\n' > main.py
git add -A && git commit -qm init

# 2. One guided command: it asks before each step. Answer y to the project
#    install; the machine-wide step is optional (y is fine — it is reversible).
ainative setup

# 3. Health, twice.
ainative status
ainative doctor
```

**Pass:** `doctor` ends healthy: no `FAIL` line, the hook is configured, the
Knowledge status is not FAIL, and the machine integration (if installed) is OK.

```bash
# 4. Declare a module and generate summaries (README steps 4-5).
cp .ai-native/templates/AI_CONTEXT_template.md AI_CONTEXT.md
python tools/ai_docs/generate_all.py
ls AI_SUMMARY.md

# 5. Now edit main.py the way you normally would, in your editor. If you use
#    Claude Code: the hook runs by itself and AI_SUMMARY.md changes.
#    Without Claude Code, run the configured command manually:
#       bash  tools/ai_docs/run_hook.sh        (Linux/macOS/Git Bash)
#       pwsh -File tools/ai_docs/run_hook.ps1  (Windows)
#    feeding it nothing on stdin is fine — it reports the empty payload on
#    stderr and never blocks.

# 6. Updates and reversal.
ainative update check          # read-only; never applies anything
ainative update                # apply if one is offered (skip if up to date)
ainative update rollback --dry-run
ainative uninstall --dry-run   # the exact list of what would be removed
```

**Pass:** `update check` answers without an error (OFFLINE is a fine answer in
a restricted network; run `ainative update check --strict` if you want it to
fail instead). The dry runs list what would happen and change nothing.

Machine-wide (only if you answered y to it in `setup`):

```bash
ainative machine status
ainative machine doctor
ainative machine repair --dry-run
ainative machine uninstall --dry-run
```

**Pass:** `status` classifies every recorded asset; `doctor` exits 0; both dry
runs list what they would do and touch nothing.

## Verified scenario (10 min, optional)

```bash
cd pilot-project
ainative init --profile verified     # or: ainative profile switch verified
ainative trust init
ainative trust bootstrap --help      # the exact bootstrap syntax for this release
```

Follow what `trust bootstrap --help` prints, commit the scaffold it asks for,
then run one small governed task:

```bash
ainative work admit                  # declare the work (see --help for the refs it wants)
ainative work new                    # create the contract the work will be judged by
ainative verify                      # run the deterministic checks
ainative converge                    # the verdict: CONVERGED or the exact missing evidence
```

**Pass:** `converge` returns a verdict — `CONVERGED` when the contract's checks
pass — and no step fabricated an authority or a fake verification. If it says
`MISSING` or `PARTIAL`, that is a valid result to report.

## Report problems

Copy the failing command and its output into an issue
(https://github.com/Rwanbt/ai-native-dev-stack/issues) with:

```
ainative --version
OS: <yours>
Python: <yours>
ainative doctor --json
the command and its output (redact tokens and personal paths)
```

Do not include secrets, tokens, or the contents of `~/.claude/`, your vault or
`.ai-native/`. `SUPPORT.md` has the full rule.

## Pass/fail checklist

| # | Check | Pass? |
|---|---|---|
| 1 | Wheel installs from the pinned release | |
| 2 | `ainative --version` prints versions | |
| 3 | `ainative setup` completes with explicit consent per step | |
| 4 | `ainative doctor` is healthy | |
| 5 | Hook entry present in `.claude/settings.json` (if Claude Code) | |
| 6 | Editing a file regenerates `AI_SUMMARY.md` | |
| 7 | `ainative update check` answers | |
| 8 | `uninstall --dry-run` lists removals, changes nothing | |
| 9 | (machine) `machine doctor` exits 0 | |
| 10 | (Verified) `converge` returns a verdict | |

Time to first success: ______ minutes. Unexpected manual step (if any):

## Feedback form

```
OS:
Python:
Harness (Claude Code / Codex / OpenCode / Cursor / none):
Install success (y/n):
Time to first success (minutes):
Doctor result (healthy / degraded / fail):
Hook worked (y/n/n-a):
Knowledge worked (y/n):
Verified onboarding worked (y/n/n-a):
Unexpected manual step:
Error (redacted):
Would you use this daily? (y/n + why):
```
