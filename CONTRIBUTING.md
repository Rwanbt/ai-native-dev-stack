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

1. Pick an open issue — `good first issue` and `help wanted` are starting
   points.
2. Comment that you are taking it; then work on a branch:

```
feat/<issue>-short-name     example: feat/23-machine-doctor
fix/<issue>-short-name      example: fix/42-safe-machine-uninstall
docs/<issue>-short-name     example: docs/7-signed-releases
```

3. Open the PR with the provided template and link the issue with
   `Closes #<n>` in the PR body.

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