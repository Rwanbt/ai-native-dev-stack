# Contributing

Thanks for improving the AI-Native Dev Stack. The bar for every change:
**leave it clean, logical, and tested.**

The universal engineering rules in [AGENTS.md](AGENTS.md) apply to every change.

## The two halves of the stack

```
ainative/                # Distribution & Lifecycle: init, status, profile
  ainative/lifecycle/    #   switch, update, uninstall, doctor, repair (stdlib-only)
ainative_workplane/      # Verified Work Plane V2: contracts, verification,
                         #   convergence. Authority architecture: ADR-0001..0008
tools/ai_docs/           # the AI-docs tooling installed into projects
hooks/                   # universal cross-agent hooks
skills/                  # first-party skills, installed into every agent root
scripts/                 # machine-level installer, vault sync, validators
stack/agents/anti-debt/  # optional anti-debt governance agent
```

Dependency direction: the lifecycle layer may invoke the Verified Work Plane;
the Work Plane never imports the lifecycle. Installing the Standard profile
loads no authority module (proved by `tests/test_lifecycle_cli.py::LayerBoundary`).

Project installation (`ainative init`) and machine-wide harness integration
(`python scripts/install_agents.py`) are separate surfaces and must stay
separate — see README.md, "What `ainative init` does".

## Verified authority architecture — frozen

The Work Plane authority model (trust bootstrap, contract admission, signer
authorization, transition evidence) is closed by adversarial review and
documented in `docs/adr/0001` through `docs/adr/0008`. **Do not change it
without a concrete, reproducible P0/P1 defect.** Open an issue first with a
reproducer; a plausible improvement is not a reason.

## Choosing work

The full method lives in [docs/GITHUB-WORKFLOW.md](docs/GITHUB-WORKFLOW.md)
and is enforced by two skills: `/github-triage` (findings to backlog) and
`/issue-to-implementation` (backlog to merged PR). The short version:

1. **Pick an open issue** — `good first issue` and `help wanted` are starting
   points. Read its Acceptance Criteria: the PR will be held to them, and
   they may only change with maintainer approval recorded on the issue.
2. **Claim visibly before working.** Take the assignment if you can;
   otherwise comment that you are taking it. If someone else claimed first
   (earliest claim wins — assignment or comment, then stable ID), let them.
3. **Work on a branch:**

```
feat/123-short-name     fix/123-short-name
docs/123-short-name     refactor/123-short-name
chore/short-name        # truly trivial, no issue required
```

4. **Implement only the issue's scope.** Unrelated findings become issues,
   not extra commits (`/github-triage`).
5. **Run the validation the issue and the repo require** (see below).
6. **Open the PR with the provided template, referencing `Refs #<n>`** — not
   `Closes` yet: the issue stays open while the PR is in review.
7. **MERGE_READY:** all acceptance criteria satisfied, tests green,
   documentation coherent, no relevant blocker. Only then does the PR body
   switch to `Closes #<n>`.
8. **Immediately before the merge, re-read the issue** and its current
   acceptance criteria (FINAL_MERGE_FRESHNESS). A material difference is
   `ISSUE_CHANGED`: stop, reconcile, never merge on a stale read.
9. **Merge through the repository's authorized process.** `DONE` = merged +
   issue closed as completed. Closed as duplicate/not-planned/invalid is not
   Done.

## Running the tests

All suites are stdlib `unittest`, zero dependencies:

```bash
# AI-docs tooling (Python 3.8+)
python -m unittest discover -s tools/ai_docs/tests -p "test_*.py"

# Vault protocol / installer / sync + hooks
python -m unittest discover -s scripts/tests -p "test_*.py"
python -m unittest discover -s hooks/tests -p "test_*.py"

# Verified Work Plane + lifecycle (Python 3.11+)
python -m unittest discover -s tests -p "test_*.py"

# Lifecycle non-vacuity and clean-install E2E (CI runs both)
python scripts/lifecycle_non_vacuity.py
python scripts/lifecycle_clean_install.py
```

CI additionally gates on: the complexity budget
(`scripts/check_complexity_budget.py`), agreement between `AGENTS.md` and
`conventions.json` (`scripts/validate_conventions.py`), the LOC gate
(`node hooks/pretool-loc-gate/run_gate.js --all`), and the `AGENTS.md` scope
table (`scripts/measure_scope.py`).

## Adding support for a new language

The most common contribution. Three steps, all test-covered:

1. **`tools/ai_docs/source_config.py`** — add the extension set (e.g.
   `ELIXIR_EXTS = {".ex", ".exs"}`) and include it in `ALL_SOURCE_EXTS`.
2. **`tools/ai_docs/generate_ai_summary.py`** — add a `parse_<lang>(path) -> dict`
   function (regex-based, best-effort) and wire it into `generate_summary()` so
   its findings render under their own headings.
3. **`tools/ai_docs/tests/`** — add a `parse_<lang>` test and, if the extension
   should trigger the hook, assert it is in `ALL_SOURCE_EXTS`.

Keep parsers conservative: a missed symbol is harmless, a false positive
pollutes the AI's context.

## Module structure requirement

Place `AI_CONTEXT.md` and all its source files in the **same flat directory**.
The scanner uses `iterdir()` (non-recursive by design). Files in subdirectories
are invisible to the hook and the summary generator.

If a subdirectory grows its own concern, promote it: add its own `AI_CONTEXT.md`.

## Conventions

- **Commits**: Conventional Commits — `feat`, `fix`, `refactor`, `perf`, `docs`,
  `test`, `chore`. One logical change per commit.
- **PRs**: <= 400 LOC of change; each PR independently mergeable. Update
  `CHANGELOG.md` under the current unreleased version section.
- **No new dependencies** in the tooling — it must run with a bare Python and
  bash/node. This is a hard constraint (the stack drops into any project).
- **Portability**: no machine-specific paths in code or docs; anything
  machine-specific belongs in `config.sh` (git-ignored) or environment
  variables.
- **Dogfood**: a new pure function gets a test in the same PR.

## Before opening a PR

Run the suites above, confirm green, then check the pre-commit checklist in
[AGENTS.md](AGENTS.md#pre-commit-checklist).