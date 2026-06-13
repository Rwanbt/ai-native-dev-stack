#!/usr/bin/env python3
"""
source_exts.py — Canonical source-file extension sets (single source of truth).

Imported by generate_ai_summary.py, update_on_edit.py, and generate_metrics.py
so that the definition of "what is a source file" lives in exactly one place.
Previously each of those scripts carried its own divergent copy (DRY violation:
a .hxx file was parsed by one tool, ignored by another).

generate_ai_summary.py needs the per-language sets for parser dispatch; the hook
and the metrics script only need the combined set. Both are exported here.
"""

CPP_EXTS    = {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"}
RUST_EXTS   = {".rs"}
TS_EXTS     = {".ts", ".tsx", ".mts"}
JS_EXTS     = {".js", ".jsx", ".mjs", ".cjs"}
PYTHON_EXTS = {".py", ".pyi"}
GO_EXTS     = {".go"}
JAVA_EXTS   = {".java"}
KOTLIN_EXTS = {".kt", ".kts"}
CS_EXTS     = {".cs"}
FS_EXTS     = {".fs", ".fsi"}
SWIFT_EXTS  = {".swift"}
RUBY_EXTS   = {".rb"}
PHP_EXTS    = {".php"}

ALL_SOURCE_EXTS = (
    CPP_EXTS | RUST_EXTS | TS_EXTS | JS_EXTS | PYTHON_EXTS |
    GO_EXTS | JAVA_EXTS | KOTLIN_EXTS | CS_EXTS | FS_EXTS |
    SWIFT_EXTS | RUBY_EXTS | PHP_EXTS
)
