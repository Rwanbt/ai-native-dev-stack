#!/usr/bin/env python3
"""
source_config.py — Shared source scanning configuration (single source of truth).

Exports:
  - Per-language extension sets (CPP_EXTS, RUST_EXTS, …)
  - ALL_SOURCE_EXTS — union of all language sets
  - EXCLUDE_DIRS — directories to skip when scanning (unified from the
    previously divergent SKIP_DIRS in generate_all.py and generate_metrics.py,
    and STOP_DIRS from module discovery).

All tools (summary generator, hook, metrics, module discovery) import from here.
"""

# --- Extension sets -----------------------------------------------------------

CPP_EXTS     = {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".inl"}
RUST_EXTS    = {".rs"}
TS_EXTS      = {".ts", ".tsx", ".mts"}
JS_EXTS      = {".js", ".jsx", ".mjs", ".cjs"}
PYTHON_EXTS  = {".py", ".pyi"}
GO_EXTS      = {".go"}
JAVA_EXTS    = {".java"}
KOTLIN_EXTS  = {".kt", ".kts"}
CS_EXTS      = {".cs"}
FS_EXTS      = {".fs", ".fsi"}
SWIFT_EXTS   = {".swift"}
RUBY_EXTS    = {".rb"}
PHP_EXTS     = {".php"}

ALL_SOURCE_EXTS = (
    CPP_EXTS | RUST_EXTS | TS_EXTS | JS_EXTS | PYTHON_EXTS |
    GO_EXTS | JAVA_EXTS | KOTLIN_EXTS | CS_EXTS | FS_EXTS |
    SWIFT_EXTS | RUBY_EXTS | PHP_EXTS
)

# --- Directory exclusions (replaces SKIP_DIRS / STOP_DIRS in all tools) ------

EXCLUDE_DIRS = {
    # VCS
    ".git", ".svn", ".hg",
    # Package managers
    "node_modules", ".pnpm-store", ".yarn", "vendor",
    # Python
    "__pycache__", ".cache", ".mypy_cache", ".pytest_cache",
    ".venv", "venv", "env", ".tox",
    # Build artifacts
    "build", "dist", "target", "out", "bin", "obj", "coverage",
    ".nyc_output",
    # IDE / tooling
    ".gradle", ".idea", ".vscode", ".next", ".parcel-cache",
}
