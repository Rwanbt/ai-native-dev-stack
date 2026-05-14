#!/usr/bin/env python3
"""
generate_ai_summary.py — Auto-generate AI_SUMMARY.md for a project module directory.

Extracts public types, Host structs, free functions, namespaces, and LOC counts
from C++ headers (.h) and Rust source files (.rs), then writes AI_SUMMARY.md.

Usage:
    python tools/ai_docs/generate_ai_summary.py <module_dir>

Output:
    <module_dir>/AI_SUMMARY.md  (always overwritten — never edit manually)
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# LOC counter (non-blank, non-comment lines)
# ---------------------------------------------------------------------------
def count_loc(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        count = 0
        in_block = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if in_block:
                if "*/" in stripped:
                    in_block = False
                continue
            if stripped.startswith("/*"):
                if "*/" not in stripped[2:]:
                    in_block = True
                continue
            if stripped.startswith("//"):
                continue
            count += 1
        return count
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# C++ header parser
# ---------------------------------------------------------------------------
def parse_cpp_header(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    result = {
        "namespaces": set(),
        "host_structs": [],
        "other_structs": [],
        "classes": [],
        "enums": [],
        "free_functions": [],
        "inline_functions": [],
    }

    # Namespaces (skip std, anonymous)
    for m in re.finditer(r"\bnamespace\s+([\w:]+)\s*\{", text):
        ns = m.group(1)
        if ns not in ("std", "detail", "impl", "internal"):
            result["namespaces"].add(ns)

    # Structs: Host structs vs plain types
    for m in re.finditer(r"^\s*struct\s+(\w+)\s*(?::\s*[\w:<>]+)?\s*\{", text, re.MULTILINE):
        name = m.group(1)
        if name.endswith("Host"):
            result["host_structs"].append(name)
        else:
            result["other_structs"].append(name)

    # Classes
    for m in re.finditer(r"^\s*class\s+(\w+)\s*(?::\s*[\w:<>\s,]+)?\s*\{", text, re.MULTILINE):
        name = m.group(1)
        if name not in result["other_structs"]:  # avoid duplicates from class/struct
            result["classes"].append(name)

    # Enums (enum / enum class)
    for m in re.finditer(r"\benum\s+(?:class\s+)?(\w+)", text):
        result["enums"].append(m.group(1))

    # Inline functions (marked with inline keyword or trivially short body on same line)
    for m in re.finditer(r"^\s*inline\s+\S.*?\s+(\w+)\s*\(", text, re.MULTILINE):
        result["inline_functions"].append(m.group(1))

    # Free functions at namespace scope (not member functions — no leading spaces before type)
    # Match lines like: void foo(... or bool bar(... or std::string baz(...
    free_fn_pat = re.compile(
        r"^(?!.*[;\{].*)\s*"                          # not inside a definition
        r"(?:void|bool|int|float|double|uint\w*|int\w*|std::[\w:]+|auto|"
        r"inline\s+\w+)\s+"
        r"(\w+)\s*\(",
        re.MULTILINE,
    )
    for m in free_fn_pat.finditer(text):
        name = m.group(1)
        if name not in result["inline_functions"] and name not in ("if", "while", "for", "switch"):
            result["free_functions"].append(name)

    # Deduplicate
    for key in ("host_structs", "other_structs", "classes", "enums", "free_functions", "inline_functions"):
        result[key] = sorted(set(result[key]))

    return result


# ---------------------------------------------------------------------------
# Rust source parser
# ---------------------------------------------------------------------------
def parse_rust_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    result = {
        "pub_structs": [],
        "pub_enums": [],
        "pub_fns": [],
        "pub_traits": [],
        "extern_c_fns": [],
    }

    for m in re.finditer(r"^pub\s+struct\s+(\w+)", text, re.MULTILINE):
        result["pub_structs"].append(m.group(1))
    for m in re.finditer(r"^pub\s+enum\s+(\w+)", text, re.MULTILINE):
        result["pub_enums"].append(m.group(1))
    for m in re.finditer(r"^pub\s+fn\s+(\w+)", text, re.MULTILINE):
        result["pub_fns"].append(m.group(1))
    for m in re.finditer(r"^pub\s+trait\s+(\w+)", text, re.MULTILINE):
        result["pub_traits"].append(m.group(1))
    # extern "C" exports
    for m in re.finditer(r'#\[no_mangle\].*?\npub\s+(?:unsafe\s+)?extern\s+"C"\s+fn\s+(\w+)', text, re.DOTALL):
        result["extern_c_fns"].append(m.group(1))

    for key in result:
        result[key] = sorted(set(result[key]))
    return result


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
        f"> Source: `tools/ai_docs/generate_ai_summary.py {module_dir.name}`",
        f"> For constraints and patterns, read `AI_CONTEXT.md` in this directory.",
        "",
    ]

    # Purpose from AI_CONTEXT.md
    context_file = module_dir / "AI_CONTEXT.md"
    if context_file.exists():
        ctx = context_file.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"## Purpose\s*\n(.*?)(?=\n##|\Z)", ctx, re.DOTALL)
        if m:
            lines += ["## Purpose", m.group(1).strip(), ""]

    # Collect source files
    h_files = sorted(module_dir.glob("*.h"))
    cpp_files = sorted(module_dir.glob("*.cpp"))
    rs_files = sorted(module_dir.glob("**/*.rs"))

    all_files = [(f, "cpp") for f in h_files + cpp_files] + [(f, "rust") for f in rs_files]

    if not all_files:
        lines.append("_No source files found in this directory._")
        return "\n".join(lines)

    # LOC table
    total_loc = 0
    file_locs = []
    for f, lang in all_files:
        loc = count_loc(f)
        total_loc += loc
        file_locs.append((f.name, loc, lang))

    lines += ["## Files & LOC", "| File | LOC | Status |", "|------|-----|--------|"]
    for name, loc, _ in sorted(file_locs):
        status = "⚠️ large" if loc > 500 else "🔴 oversized" if loc > 1500 else "✅"
        lines.append(f"| `{name}` | {loc} | {status} |")
    lines += [f"| **Total** | **{total_loc}** | |", ""]

    # Aggregate C++ info from headers only
    cpp_agg = {
        "namespaces": set(),
        "host_structs": [],
        "other_structs": [],
        "classes": [],
        "enums": [],
        "free_functions": [],
        "inline_functions": [],
    }
    for f in h_files:
        parsed = parse_cpp_header(f)
        cpp_agg["namespaces"].update(parsed["namespaces"])
        cpp_agg["host_structs"].extend(parsed["host_structs"])
        cpp_agg["other_structs"].extend(parsed["other_structs"])
        cpp_agg["classes"].extend(parsed["classes"])
        cpp_agg["enums"].extend(parsed["enums"])
        cpp_agg["free_functions"].extend(parsed["free_functions"])
        cpp_agg["inline_functions"].extend(parsed["inline_functions"])

    # Aggregate Rust info
    rust_agg = {
        "pub_structs": [],
        "pub_enums": [],
        "pub_fns": [],
        "pub_traits": [],
        "extern_c_fns": [],
    }
    for f in rs_files:
        parsed = parse_rust_file(f)
        for key in rust_agg:
            rust_agg[key].extend(parsed[key])

    # Namespaces
    if cpp_agg["namespaces"]:
        ns_str = "`, `".join(sorted(cpp_agg["namespaces"]))
        lines += [f"**C++ Namespace(s)**: `{ns_str}`", ""]

    # Host structs (the module's public interface)
    host_structs = sorted(set(cpp_agg["host_structs"]))
    if host_structs:
        lines += ["## Host Structs (module interface)"]
        for s in host_structs:
            lines.append(f"- `{s}`")
        lines.append("")

    # Other public types
    other_types = sorted(set(cpp_agg["other_structs"] + cpp_agg["classes"]))
    if other_types:
        lines += ["## Other Types"]
        for t in other_types:
            lines.append(f"- `{t}`")
        lines.append("")

    # Enums
    enums = sorted(set(cpp_agg["enums"]))
    if enums:
        lines += ["## Enums"]
        for e in enums:
            lines.append(f"- `{e}`")
        lines.append("")

    # Free functions
    free_fns = sorted(set(cpp_agg["free_functions"]))
    if free_fns:
        lines += ["## Public Free Functions"]
        for fn in free_fns:
            lines.append(f"- `{fn}()`")
        lines.append("")

    # Inline functions (read-only queries, no host)
    inline_fns = sorted(set(cpp_agg["inline_functions"]))
    if inline_fns:
        lines += ["## Inline Queries (no host needed)"]
        for fn in inline_fns:
            lines.append(f"- `{fn}()`")
        lines.append("")

    # Rust public API
    if rust_agg["pub_structs"] or rust_agg["pub_enums"] or rust_agg["pub_fns"] or rust_agg["pub_traits"]:
        lines += ["## Rust Public API"]
        for t in sorted(set(rust_agg["pub_structs"])):
            lines.append(f"- `{t}` (struct)")
        for t in sorted(set(rust_agg["pub_enums"])):
            lines.append(f"- `{t}` (enum)")
        for t in sorted(set(rust_agg["pub_traits"])):
            lines.append(f"- `{t}` (trait)")
        lines.append("")

    if rust_agg["pub_fns"]:
        lines += ["## Rust Public Functions"]
        for fn in sorted(set(rust_agg["pub_fns"])):
            lines.append(f"- `{fn}()`")
        lines.append("")

    if rust_agg["extern_c_fns"]:
        lines += ["## extern \"C\" FFI Exports"]
        for fn in sorted(set(rust_agg["extern_c_fns"])):
            lines.append(f"- `{fn}()`")
        lines.append("")

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

    summary = generate_summary(module_dir)
    out = module_dir / "AI_SUMMARY.md"
    out.write_text(summary, encoding="utf-8")
    print(f"Updated {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
