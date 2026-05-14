#!/usr/bin/env python3
"""
generate_ai_summary.py — Auto-generate AI_SUMMARY.md for any project module.

Supports: C/C++, Rust, TypeScript/JavaScript, Python, Go, Java/Kotlin, C#/F#, Swift, Ruby, PHP.
Extracts public types, functions, classes, LOC counts, and thread annotations.

Usage:
    python tools/ai_docs/generate_ai_summary.py <module_dir>

Output:
    <module_dir>/AI_SUMMARY.md  (always overwritten — never edit manually)
"""

import re
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# LOC counter — non-blank, non-pure-comment lines
# ---------------------------------------------------------------------------
def count_loc(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        count = 0
        in_block = False
        for line in lines:
            s = line.strip()
            if not s:
                continue
            # Block comments (/* ... */ and """ ... """)
            if in_block:
                if "*/" in s or '"""' in s or "'''" in s:
                    in_block = False
                continue
            if s.startswith("/*") or s.startswith('"""') or s.startswith("'''"):
                if "*/" not in s[2:] and '"""' not in s[3:] and "'''" not in s[3:]:
                    in_block = True
                continue
            # Line comments
            if s.startswith("//") or s.startswith("#") or s.startswith("--"):
                continue
            count += 1
        return count
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# C / C++ parser
# ---------------------------------------------------------------------------
def parse_cpp(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"namespaces": set(), "host_structs": [], "structs": [], "classes": [],
         "enums": [], "free_functions": [], "inline_functions": [], "thread_annotations": []}

    for m in re.finditer(r"\bnamespace\s+([\w:]+)\s*\{", text):
        ns = m.group(1)
        if ns not in ("std", "detail", "impl", "internal", "anonymous"):
            r["namespaces"].add(ns)

    for m in re.finditer(r"^\s*struct\s+(\w+)\b", text, re.MULTILINE):
        name = m.group(1)
        (r["host_structs"] if name.endswith("Host") else r["structs"]).append(name)

    for m in re.finditer(r"^\s*class\s+(\w+)\b", text, re.MULTILINE):
        r["classes"].append(m.group(1))

    for m in re.finditer(r"\benum\s+(?:class\s+)?(\w+)\b", text):
        r["enums"].append(m.group(1))

    for m in re.finditer(r"^\s*inline\s+\S.*?\s+(\w+)\s*\(", text, re.MULTILINE):
        r["inline_functions"].append(m.group(1))

    # Free functions: type name( at start of line, no leading indent (namespace scope)
    for m in re.finditer(
        r"^(?:void|bool|int|float|double|auto|uint\w*|int\w*|std::[\w:<>]+)\s+(\w+)\s*\(",
        text, re.MULTILINE
    ):
        name = m.group(1)
        if name not in r["inline_functions"] and name not in {"if", "while", "for", "switch"}:
            r["free_functions"].append(name)

    for m in re.finditer(r"//\s*(THREAD:|AUDIO_THREAD_ONLY|RT_SAFE|MAIN_THREAD|@thread)", text):
        r["thread_annotations"].append(m.group(1).strip())

    for key in r:
        if isinstance(r[key], list):
            r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# Rust parser
# ---------------------------------------------------------------------------
def parse_rust(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"pub_structs": [], "pub_enums": [], "pub_fns": [], "pub_traits": [], "extern_c_fns": []}

    for m in re.finditer(r"^pub\s+(?:async\s+)?struct\s+(\w+)", text, re.MULTILINE):
        r["pub_structs"].append(m.group(1))
    for m in re.finditer(r"^pub\s+enum\s+(\w+)", text, re.MULTILINE):
        r["pub_enums"].append(m.group(1))
    for m in re.finditer(r"^pub\s+(?:async\s+)?fn\s+(\w+)", text, re.MULTILINE):
        r["pub_fns"].append(m.group(1))
    for m in re.finditer(r"^pub\s+trait\s+(\w+)", text, re.MULTILINE):
        r["pub_traits"].append(m.group(1))
    for m in re.finditer(r'#\[no_mangle\].*?pub\s+(?:unsafe\s+)?extern\s+"C"\s+fn\s+(\w+)',
                         text, re.DOTALL):
        r["extern_c_fns"].append(m.group(1))

    for key in r:
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# TypeScript / JavaScript parser
# ---------------------------------------------------------------------------
def parse_typescript(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"classes": [], "interfaces": [], "types": [], "enums": [],
         "exported_functions": [], "exported_consts": []}

    for m in re.finditer(r"^export\s+(?:abstract\s+)?class\s+(\w+)", text, re.MULTILINE):
        r["classes"].append(m.group(1))
    for m in re.finditer(r"^export\s+interface\s+(\w+)", text, re.MULTILINE):
        r["interfaces"].append(m.group(1))
    for m in re.finditer(r"^export\s+type\s+(\w+)\s*[=<{]", text, re.MULTILINE):
        r["types"].append(m.group(1))
    for m in re.finditer(r"^export\s+enum\s+(\w+)", text, re.MULTILINE):
        r["enums"].append(m.group(1))
    for m in re.finditer(
        r"^export\s+(?:async\s+)?function\s+(\w+)|^export\s+(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(",
        text, re.MULTILINE
    ):
        name = m.group(1) or m.group(2)
        if name:
            r["exported_functions"].append(name)
    for m in re.finditer(r"^export\s+const\s+(\w+)\s*(?::\s*\S+)?\s*=\s*[^(]", text, re.MULTILINE):
        r["exported_consts"].append(m.group(1))

    for key in r:
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# Python parser
# ---------------------------------------------------------------------------
def parse_python(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"classes": [], "public_functions": [], "dataclasses": []}

    for m in re.finditer(r"^@dataclass[^\n]*\nclass\s+(\w+)", text, re.MULTILINE):
        r["dataclasses"].append(m.group(1))
    for m in re.finditer(r"^class\s+(\w+)", text, re.MULTILINE):
        r["classes"].append(m.group(1))
    for m in re.finditer(r"^def\s+([a-z]\w*)\s*\(", text, re.MULTILINE):
        r["public_functions"].append(m.group(1))

    for key in r:
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# Go parser
# ---------------------------------------------------------------------------
def parse_go(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"types": [], "interfaces": [], "exported_funcs": [], "packages": []}

    for m in re.finditer(r"^package\s+(\w+)", text, re.MULTILINE):
        r["packages"].append(m.group(1))
    for m in re.finditer(r"^type\s+([A-Z]\w*)\s+interface", text, re.MULTILINE):
        r["interfaces"].append(m.group(1))
    for m in re.finditer(r"^type\s+([A-Z]\w*)\s+struct", text, re.MULTILINE):
        r["types"].append(m.group(1))
    for m in re.finditer(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?([A-Z]\w*)\s*\(", text, re.MULTILINE):
        r["exported_funcs"].append(m.group(1))

    for key in r:
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# Java / Kotlin parser
# ---------------------------------------------------------------------------
def parse_java(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"classes": [], "interfaces": [], "enums": [], "public_methods": []}

    for m in re.finditer(r"\bpublic\s+(?:abstract\s+)?class\s+(\w+)", text):
        r["classes"].append(m.group(1))
    for m in re.finditer(r"\bpublic\s+interface\s+(\w+)", text):
        r["interfaces"].append(m.group(1))
    for m in re.finditer(r"\bpublic\s+enum\s+(\w+)", text):
        r["enums"].append(m.group(1))
    for m in re.finditer(r"\bpublic\s+(?:static\s+)?(?:final\s+)?(?:\w+\s+)+(\w+)\s*\(", text):
        name = m.group(1)
        if name not in r["classes"] and name not in r["interfaces"]:
            r["public_methods"].append(name)

    for key in r:
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# C# parser
# ---------------------------------------------------------------------------
def parse_csharp(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"classes": [], "interfaces": [], "enums": [], "public_methods": [], "namespaces": set()}

    for m in re.finditer(r"\bnamespace\s+([\w.]+)", text):
        r["namespaces"].add(m.group(1))
    for m in re.finditer(r"\bpublic\s+(?:abstract\s+|sealed\s+|static\s+)?class\s+(\w+)", text):
        r["classes"].append(m.group(1))
    for m in re.finditer(r"\bpublic\s+interface\s+(\w+)", text):
        r["interfaces"].append(m.group(1))
    for m in re.finditer(r"\bpublic\s+enum\s+(\w+)", text):
        r["enums"].append(m.group(1))

    r["namespaces"] = sorted(r["namespaces"])
    for key in ("classes", "interfaces", "enums"):
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# Generic fallback (Swift, Ruby, PHP, etc.)
# ---------------------------------------------------------------------------
def parse_generic(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    r = {"classes": [], "functions": []}

    # Heuristic: look for class/def/func keywords
    for m in re.finditer(r"(?:class|struct|interface|trait)\s+([A-Z]\w*)", text):
        r["classes"].append(m.group(1))
    for m in re.finditer(r"(?:def|func|function|sub|method)\s+([a-z_]\w*)\s*\(", text):
        r["functions"].append(m.group(1))

    for key in r:
        r[key] = sorted(set(r[key]))
    return r


# ---------------------------------------------------------------------------
# Summary renderer
# ---------------------------------------------------------------------------
def generate_summary(module_dir: Path) -> str:
    module_name = module_dir.name
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# AI_SUMMARY — {module_name}",
        "",
        f"> **Auto-generated {now}** — do not edit manually.",
        f"> Source: `tools/ai_docs/generate_ai_summary.py`",
        f"> For purpose, thread model and constraints, read `AI_CONTEXT.md`.",
        "",
    ]

    # Pull Purpose from AI_CONTEXT.md if present
    ctx = module_dir / "AI_CONTEXT.md"
    if ctx.exists():
        text = ctx.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"## Purpose\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        if m:
            lines += ["## Purpose", m.group(1).strip(), ""]

    # Collect source files
    source_files = [
        f for f in sorted(module_dir.iterdir())
        if f.is_file() and f.suffix.lower() in ALL_SOURCE_EXTS
        and f.name != "AI_SUMMARY.md"
    ]

    if not source_files:
        lines.append("_No source files found in this directory._")
        return "\n".join(lines)

    # LOC table
    total = 0
    rows = []
    for f in source_files:
        loc = count_loc(f)
        total += loc
        flag = " 🔴" if loc > 1500 else " ⚠️" if loc > 500 else ""
        rows.append((f.name, loc, flag))

    lines += ["## Files & LOC", "| File | LOC | |", "|------|-----|--|"]
    for name, loc, flag in rows:
        lines.append(f"| `{name}` | {loc} |{flag} |")
    lines += [f"| **Total** | **{total}** | |", ""]

    # --- Language-specific sections ---

    # C / C++
    cpp_files = [f for f in source_files if f.suffix.lower() in CPP_EXTS]
    if cpp_files:
        agg: dict = {"namespaces": set(), "host_structs": [], "structs": [], "classes": [],
                     "enums": [], "free_functions": [], "inline_functions": []}
        for f in cpp_files:
            p = parse_cpp(f)
            agg["namespaces"].update(p["namespaces"])
            for k in ("host_structs", "structs", "classes", "enums", "free_functions", "inline_functions"):
                agg[k].extend(p[k])

        if agg["namespaces"]:
            lines += [f"**Namespace(s)**: `{'`, `'.join(sorted(agg['namespaces']))}`", ""]
        if agg["host_structs"]:
            lines += ["## Host Structs"] + [f"- `{s}`" for s in sorted(set(agg["host_structs"]))] + [""]
        other_types = sorted(set(agg["structs"] + agg["classes"]))
        if other_types:
            lines += ["## Types"] + [f"- `{t}`" for t in other_types] + [""]
        if agg["enums"]:
            lines += ["## Enums"] + [f"- `{e}`" for e in sorted(set(agg["enums"]))] + [""]
        if agg["free_functions"]:
            lines += ["## Free Functions"] + [f"- `{f}()`" for f in sorted(set(agg["free_functions"]))] + [""]
        if agg["inline_functions"]:
            lines += ["## Inline Queries"] + [f"- `{f}()`" for f in sorted(set(agg["inline_functions"]))] + [""]

    # Rust
    rust_files = [f for f in source_files if f.suffix.lower() in RUST_EXTS]
    if rust_files:
        agg_r: dict = {"pub_structs": [], "pub_enums": [], "pub_fns": [], "pub_traits": [], "extern_c_fns": []}
        for f in rust_files:
            p = parse_rust(f)
            for k in agg_r:
                agg_r[k].extend(p[k])
        if any(agg_r.values()):
            lines.append("## Rust API")
            for t in sorted(set(agg_r["pub_structs"])): lines.append(f"- `{t}` (struct)")
            for t in sorted(set(agg_r["pub_enums"])): lines.append(f"- `{t}` (enum)")
            for t in sorted(set(agg_r["pub_traits"])): lines.append(f"- `{t}` (trait)")
            lines.append("")
        if agg_r["pub_fns"]:
            lines += ["## Rust Functions"] + [f"- `{f}()`" for f in sorted(set(agg_r["pub_fns"]))] + [""]
        if agg_r["extern_c_fns"]:
            lines += ['## extern "C" Exports'] + [f"- `{f}()`" for f in sorted(set(agg_r["extern_c_fns"]))] + [""]

    # TypeScript / JavaScript
    ts_files = [f for f in source_files if f.suffix.lower() in TS_EXTS | JS_EXTS]
    if ts_files:
        agg_t: dict = {"classes": [], "interfaces": [], "types": [], "enums": [], "exported_functions": [], "exported_consts": []}
        for f in ts_files:
            p = parse_typescript(f)
            for k in agg_t:
                agg_t[k].extend(p[k])
        for label, key in [("## TS/JS Classes", "classes"), ("## Interfaces", "interfaces"),
                            ("## Types", "types"), ("## Enums", "enums"),
                            ("## Exported Functions", "exported_functions"),
                            ("## Exported Constants", "exported_consts")]:
            items = sorted(set(agg_t[key]))
            if items:
                lines += [label] + [f"- `{i}`" for i in items] + [""]

    # Python
    py_files = [f for f in source_files if f.suffix.lower() in PYTHON_EXTS]
    if py_files:
        agg_py: dict = {"classes": [], "dataclasses": [], "public_functions": []}
        for f in py_files:
            p = parse_python(f)
            for k in agg_py:
                agg_py[k].extend(p[k])
        for label, key in [("## Classes", "classes"), ("## Dataclasses", "dataclasses"),
                            ("## Public Functions", "public_functions")]:
            items = sorted(set(agg_py[key]))
            if items:
                lines += [label] + [f"- `{i}`" for i in items] + [""]

    # Go
    go_files = [f for f in source_files if f.suffix.lower() in GO_EXTS]
    if go_files:
        agg_go: dict = {"packages": [], "types": [], "interfaces": [], "exported_funcs": []}
        for f in go_files:
            p = parse_go(f)
            for k in agg_go:
                agg_go[k].extend(p[k])
        pkgs = sorted(set(agg_go["packages"]))
        if pkgs:
            lines += [f"**Package(s)**: `{'`, `'.join(pkgs)}`", ""]
        for label, key in [("## Go Types", "types"), ("## Go Interfaces", "interfaces"),
                            ("## Exported Functions", "exported_funcs")]:
            items = sorted(set(agg_go[key]))
            if items:
                lines += [label] + [f"- `{i}`" for i in items] + [""]

    # Java / Kotlin
    jk_files = [f for f in source_files if f.suffix.lower() in JAVA_EXTS | KOTLIN_EXTS]
    if jk_files:
        agg_j: dict = {"classes": [], "interfaces": [], "enums": [], "public_methods": []}
        for f in jk_files:
            p = parse_java(f)
            for k in agg_j:
                agg_j[k].extend(p[k])
        for label, key in [("## Classes", "classes"), ("## Interfaces", "interfaces"),
                            ("## Enums", "enums"), ("## Public Methods", "public_methods")]:
            items = sorted(set(agg_j[key]))
            if items:
                lines += [label] + [f"- `{i}`" for i in items] + [""]

    # C#
    cs_files = [f for f in source_files if f.suffix.lower() in CS_EXTS | FS_EXTS]
    if cs_files:
        agg_cs: dict = {"namespaces": [], "classes": [], "interfaces": [], "enums": []}
        for f in cs_files:
            p = parse_csharp(f)
            agg_cs["namespaces"].extend(p["namespaces"])
            for k in ("classes", "interfaces", "enums"):
                agg_cs[k].extend(p[k])
        if agg_cs["namespaces"]:
            lines += [f"**Namespace(s)**: `{'`, `'.join(sorted(set(agg_cs['namespaces'])))}`", ""]
        for label, key in [("## Classes", "classes"), ("## Interfaces", "interfaces"), ("## Enums", "enums")]:
            items = sorted(set(agg_cs[key]))
            if items:
                lines += [label] + [f"- `{i}`" for i in items] + [""]

    # Generic fallback (Swift, Ruby, PHP, etc.)
    generic_files = [
        f for f in source_files
        if f.suffix.lower() in SWIFT_EXTS | RUBY_EXTS | PHP_EXTS
    ]
    if generic_files:
        agg_g: dict = {"classes": [], "functions": []}
        for f in generic_files:
            p = parse_generic(f)
            for k in agg_g:
                agg_g[k].extend(p[k])
        for label, key in [("## Classes", "classes"), ("## Functions", "functions")]:
            items = sorted(set(agg_g[key]))
            if items:
                lines += [label] + [f"- `{i}`" for i in items] + [""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: generate_ai_summary.py <module_dir>", file=sys.stderr)
        return 1

    module_dir = Path(sys.argv[1]).resolve()
    if not module_dir.is_dir():
        print(f"Not a directory: {module_dir}", file=sys.stderr)
        return 1

    out = module_dir / "AI_SUMMARY.md"
    out.write_text(generate_summary(module_dir), encoding="utf-8")
    print(f"Updated {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
