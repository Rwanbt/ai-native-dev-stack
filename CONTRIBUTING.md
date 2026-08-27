# Contributing

Thanks for improving the AI-Native Dev Stack. This repo is small and
script-driven; the bar is: **leave it clean, logical, and tested.**

The universal engineering rules in [AGENTS.md](AGENTS.md) apply to every change.

## Repository layout

```
tools/ai_docs/         # the executable stack (Python + bash)
  source_config.py     # single source of truth for source-file extensions and directory exclusions
  generate_ai_summary.py  # AI_SUMMARY.md generator (per-language parsers)
  update_on_edit.py    # PostToolUse hook entry point
  run_hook.sh          # hook wrapper (finds Python, delegates)
  find_python.sh       # locates a working Python 3.8+ interpreter
  generate_all.py      # regenerate every module's AI_SUMMARY.md
  generate_metrics.py  # docs/METRICS.md snapshot
  assemble_context.py  # one-shot context briefing for a source file
  tests/               # zero-dependency unittest suite
skills/                # first-party skills, installed into every agent root
templates/             # AI_CONTEXT template + hook settings example
conventions.json       # machine-readable twin of AGENTS.md's thresholds
install.py             # per-project installer (install.sh / .ps1 are shims)
scripts/
  install_agents.py    # machine-level installer (setup-agents.sh / .ps1 shims)
  validate_conventions.py  # fails when AGENTS.md and conventions.json disagree
  measure_scope.py     # fails when AGENTS.md's scope table drifts from reality
  vault_sync.py        # Obsidian vault sync (vault_sync.ps1 / .sh are shims)
```

Every installer and check is one cross-platform Python implementation; the
`.sh` and `.ps1` files only locate an interpreter and delegate. Add behaviour
to the Python file, never to a shim — two shells means two versions to drift.

## Running the tests

Zero dependencies — stdlib `unittest` only:

```bash
python -m unittest discover -s tools/ai_docs/tests -p "test_*.py" -v
```

CI runs this on Python 3.8 (legacy, EOL) / 3.9 / 3.11 / 3.13, plus a 1500-LOC gate (raw lines). Both must pass.

## Module structure requirement

Place `AI_CONTEXT.md` and all its source files in the **same flat directory**.
The scanner uses `iterdir()` (non-recursive by design). Files in subdirectories
are invisible to the hook and the summary generator.

```
✅ Valid                    ❌ Invalid (nested files ignored)
my_module/                  my_module/
├── AI_CONTEXT.md           ├── AI_CONTEXT.md
├── service.py              ├── sub/
└── utils.py                │   └── service.py   ← NOT scanned
                            └── utils.py
```

If a subdirectory grows its own concern, promote it: add its own `AI_CONTEXT.md`.

## Adding support for a new language

The most common contribution. Three steps, all test-covered:

1. **`source_config.py`** — add the extension set (e.g. `ELIXIR_EXTS = {".ex", ".exs"}`)
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
