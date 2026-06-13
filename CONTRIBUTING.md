# Contributing

Thanks for improving the AI-Native Dev Stack. This repo is small and
script-driven; the bar is: **leave it clean, logical, and tested.**

The universal engineering rules in [AGENTS.md](AGENTS.md) apply to every change.

## Repository layout

```
tools/ai_docs/         # the executable stack (Python + bash)
  source_exts.py       # single source of truth for source-file extensions
  generate_ai_summary.py  # AI_SUMMARY.md generator (per-language parsers)
  update_on_edit.py    # PostToolUse hook entry point
  run_hook.sh          # hook wrapper (finds Python, delegates)
  find_python.sh       # locates a working Python 3.8+ interpreter
  generate_all.py      # regenerate every module's AI_SUMMARY.md
  generate_metrics.py  # docs/METRICS.md snapshot
  assemble_context.py  # one-shot context briefing for a source file
  tests/               # zero-dependency unittest suite
skills/                # Claude Code skills (verify-ai-docs, verify-standards)
templates/             # AI_CONTEXT template + hook settings example
install.sh             # installs the stack into a target project
```

## Running the tests

Zero dependencies — stdlib `unittest` only:

```bash
python -m unittest discover -s tools/ai_docs/tests -p "test_*.py" -v
```

CI runs this on Python 3.9 / 3.11 / 3.13, plus a 1500-LOC gate. Both must pass.

## Adding support for a new language

The most common contribution. Three steps, all test-covered:

1. **`source_exts.py`** — add the extension set (e.g. `ELIXIR_EXTS = {".ex", ".exs"}`)
   and include it in `ALL_SOURCE_EXTS`.
2. **`generate_ai_summary.py`** — add a `parse_<lang>(path) -> dict` function
   (regex-based, best-effort) and wire it into `generate_summary()` so its
   findings render under their own headings.
3. **`tests/test_ai_docs.py`** — add a `parse_<lang>` test and, if the extension
   should trigger the hook, assert it is in `ALL_SOURCE_EXTS`.

Keep parsers conservative: a missed symbol is harmless, a false positive
pollutes the AI's context.

## Conventions

- **Commits**: Conventional Commits — `feat`, `fix`, `refactor`, `perf`, `docs`,
  `test`, `chore`. One logical change per commit.
- **PRs**: ≤ 400 LOC of change; each PR independently mergeable. Update
  `CHANGELOG.md` under `[Unreleased]`.
- **No new dependencies** in the tooling — it must run with a bare Python 3.8+
  and bash. This is a hard constraint (the stack drops into any project).
- **Portability**: no machine-specific paths; anything machine-specific belongs
  in `config.sh` (git-ignored).
- **Dogfood**: a new pure function gets a test in the same PR.

## Before opening a PR

Run, and confirm green:

```bash
python -m unittest discover -s tools/ai_docs/tests -p "test_*.py"
```

Then check the box list in [AGENTS.md](AGENTS.md#pre-commit-checklist).
