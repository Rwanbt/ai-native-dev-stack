#!/usr/bin/env python3
"""polyglot_scan.py — Lightweight static analysis for Rust and JavaScript/TypeScript.

Used when clippy/eslint is not installed. Pure regex/AST-heuristic — best-effort.
- Rust: function-level cyclomatic complexity, god-function detection, hardcoded secrets
- JS/TS: import cycle detection, hardcoded secrets, large functions

Output: JSON list of debt-finding objects on stdout.
"""
from __future__ import annotations
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finding_common import finding_id, SECRET_PATTERNS  # noqa: E402

CC_THRESHOLD = 10
CC_CRITICAL = 20
GOD_FUNC_LINES = 40
GOD_FUNC_CC = 12
FUNC_LINES_WARN = 50
FUNC_LINES_HIGH = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding(file: Path, line: int, category: str, subcategory: str, severity: str,
              description: str, evidence: list, confidence: float = 0.85,
              discriminator: str = "") -> dict:
    return {
        "id": finding_id(category, subcategory, str(file), str(line), discriminator),
        "category": category,
        "subcategory": subcategory,
        "severity": severity,
        "location": {"file": str(file), "lines": f"{line}"},
        "description": description,
        "evidence": evidence,
        "confidence": confidence,
        "source": "tool:polyglot-scan",
        "estimated_effort": "S",
        "risk_of_fix": "medium",
        "auto_fixable": False,
        "first_seen": _now(),
        "last_seen": _now(),
    }


# ---------- Rust ----------

RUST_FN_RE = re.compile(
    r'^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:const\s+)?(?:unsafe\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)',
    re.MULTILINE
)


def _rust_function_blocks(source: str) -> list[tuple[str, int, int, str]]:
    """Return [(name, start_line, end_line, body)] for each Rust function.

    Brace-matching based — robust to nested braces.
    """
    results = []
    for m in RUST_FN_RE.finditer(source):
        name = m.group(1)
        start = source[:m.start()].count("\n") + 1
        # Find the opening brace after the signature
        rest = source[m.end():]
        brace_idx = rest.find("{")
        if brace_idx < 0:
            continue
        # Count braces to find the matching close
        depth = 0
        i = brace_idx
        while i < len(rest):
            if rest[i] == "{":
                depth += 1
            elif rest[i] == "}":
                depth -= 1
                if depth == 0:
                    end = m.end() + i + 1
                    end_line = source[:end].count("\n") + 1
                    body = rest[brace_idx:i+1]
                    results.append((name, start, end_line, body))
                    break
            i += 1
    return results


def _rust_cc(body: str) -> int:
    """Count cyclomatic complexity of a Rust function body."""
    cc = 1
    cc += len(re.findall(r'\bif\b', body))
    cc += len(re.findall(r'\belse\s+if\b', body))
    cc += len(re.findall(r'\belse\s+if\s+let\b', body))
    cc += len(re.findall(r'\bfor\b', body))
    cc += len(re.findall(r'\bwhile\b', body))
    cc += len(re.findall(r'\bmatch\b', body))
    # each match arm counts
    cc += len(re.findall(r'=>\s*\{', body))
    cc += len(re.findall(r'\?\s*(?:;|$|\s|\})', body, re.MULTILINE))  # ? operator
    cc += len(re.findall(r'\bif\s+let\b', body))
    return cc


def scan_rust_file(path: Path) -> list[dict]:
    findings: list = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    # 1. Per-function metrics
    for name, start, end, body in _rust_function_blocks(source):
        cc = _rust_cc(body)
        n_lines = end - start + 1
        if cc >= CC_CRITICAL:
            findings.append(_finding(path, start, "code", "complexity", "high",
                description=f"Rust function '{name}' has cyclomatic complexity {cc} (>= {CC_CRITICAL})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} cc={cc}"},
                ]))
        elif cc >= CC_THRESHOLD:
            findings.append(_finding(path, start, "code", "complexity", "medium",
                description=f"Rust function '{name}' has cyclomatic complexity {cc} (>= {CC_THRESHOLD})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} cc={cc}"},
                ]))
        if n_lines >= FUNC_LINES_HIGH:
            findings.append(_finding(path, start, "code", "long_function", "high",
                description=f"Rust function '{name}' is {n_lines} lines long (>= {FUNC_LINES_HIGH})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} lines={n_lines}"},
                ]))
        elif n_lines >= FUNC_LINES_WARN:
            findings.append(_finding(path, start, "code", "long_function", "medium",
                description=f"Rust function '{name}' is {n_lines} lines long (>= {FUNC_LINES_WARN})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} lines={n_lines}"},
                ]))
        # God function: long AND complex
        if n_lines > GOD_FUNC_LINES and cc > GOD_FUNC_CC:
            findings.append(_finding(path, start, "code", "god_classes", "medium",
                description=f"Rust function '{name}' is a god function: {n_lines} lines, CC={cc}",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} lines={n_lines} cc={cc}"},
                ]))
    # 2. Secret patterns
    for lineno, line in enumerate(source.splitlines(), start=1):
        for pat, label in SECRET_PATTERNS:
            if pat.search(line):
                findings.append(_finding(path, lineno, "security", "secrets_in_code", "critical",
                    description=f"Hardcoded {label}",
                    evidence=[
                        {"type": "file_location", "value": f"{path}:{lineno}"},
                        {"type": "regex_match", "tool": "polyglot-scan", "value": line.strip()[:120]},
                    ]))
                break
    return findings


def scan_rust_repo(root: Path) -> list[dict]:
    findings: list = []
    skip_dirs = {"target", ".git", "node_modules"}
    for rs in root.rglob("*.rs"):
        if any(part in skip_dirs for part in rs.parts):
            continue
        findings.extend(scan_rust_file(rs))
    return findings


# ---------- JavaScript / TypeScript ----------

JS_IMPORT_RE = re.compile(
    r'''(?:
        import\s+(?:[^'"`]+from\s+)?['"`]([^'"`]+)['"`]      # import x from "y"
        |
        require\s*\(\s*['"`]([^'"`]+)['"`]\s*\)              # require("y")
        |
        import\s*\(\s*['"`]([^'"`]+)['"`]\s*\)               # dynamic import("y")
    )''',
    re.VERBOSE
)
JS_FN_RE = re.compile(
    r'(?:function\s+([A-Za-z_$][\w$]*)\s*\(|'
    r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function|\()|'
    r'(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*=>)',
    re.MULTILINE
)


def _js_function_blocks(source: str) -> list[tuple[str, int, int, str]]:
    """Best-effort function block extraction for JS/TS."""
    results = []
    for m in JS_FN_RE.finditer(source):
        name = m.group(1) or m.group(2) or m.group(3) or "<anonymous>"
        start = source[:m.start()].count("\n") + 1
        # Find the matching closing brace
        rest = source[m.end():]
        # Skip to first { or end of arrow if single-expression
        if "=>" in m.group(0) and "{" not in rest[:rest.find(";") if ";" in rest else len(rest)]:
            # Single-expression arrow: take up to the next semicolon or newline
            sem = rest.find(";")
            nl = rest.find("\n")
            if sem < 0 or (nl >= 0 and nl < sem):
                end = m.end() + nl if nl >= 0 else m.end() + sem
            else:
                end = m.end() + sem
            end_line = source[:end].count("\n") + 1
            body = rest[:end - m.end()]
            results.append((name, start, end_line, body))
            continue
        brace_idx = rest.find("{")
        if brace_idx < 0:
            continue
        depth = 0
        i = brace_idx
        while i < len(rest):
            if rest[i] == "{":
                depth += 1
            elif rest[i] == "}":
                depth -= 1
                if depth == 0:
                    end = m.end() + i + 1
                    end_line = source[:end].count("\n") + 1
                    body = rest[brace_idx:i+1]
                    results.append((name, start, end_line, body))
                    break
            i += 1
    return results


def _js_cc(body: str) -> int:
    cc = 1
    cc += len(re.findall(r'\bif\b', body))
    cc += len(re.findall(r'\belse\s+if\b', body))
    cc += len(re.findall(r'\bfor\b', body))
    cc += len(re.findall(r'\bwhile\b', body))
    cc += len(re.findall(r'\bcase\s+', body))
    cc += len(re.findall(r'\?\s*[^:]', body))  # ternary
    cc += len(re.findall(r'\bawait\b', body)) // 2  # partial credit
    return cc


def scan_js_file(path: Path) -> list[dict]:
    findings: list = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for name, start, end, body in _js_function_blocks(source):
        cc = _js_cc(body)
        n_lines = end - start + 1
        if cc >= CC_CRITICAL:
            findings.append(_finding(path, start, "code", "complexity", "high",
                description=f"JS function '{name}' has cyclomatic complexity {cc} (>= {CC_CRITICAL})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} cc={cc}"},
                ]))
        elif cc >= CC_THRESHOLD:
            findings.append(_finding(path, start, "code", "complexity", "medium",
                description=f"JS function '{name}' has cyclomatic complexity {cc} (>= {CC_THRESHOLD})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{start}"},
                    {"type": "ast_metric", "tool": "polyglot-scan", "value": f"function={name} cc={cc}"},
                ]))
    for lineno, line in enumerate(source.splitlines(), start=1):
        for pat, label in SECRET_PATTERNS:
            if pat.search(line):
                findings.append(_finding(path, lineno, "security", "secrets_in_code", "critical",
                    description=f"Hardcoded {label}",
                    evidence=[
                        {"type": "file_location", "value": f"{path}:{lineno}"},
                        {"type": "regex_match", "tool": "polyglot-scan", "value": line.strip()[:120]},
                    ]))
                break
    return findings


def detect_js_cycles(root: Path) -> list[dict]:
    """Detect circular dependencies between JS/TS files."""
    findings: list = []
    skip_dirs = {"node_modules", "dist", "build", ".git"}
    files = [p for p in list(root.rglob("*.ts")) + list(root.rglob("*.js")) + list(root.rglob("*.tsx")) + list(root.rglob("*.jsx"))
             if not any(part in skip_dirs for part in p.parts)]
    # Build adjacency: file -> set of imported files (resolved)
    adj: dict[Path, set[Path]] = defaultdict(set)
    for f in files:
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in JS_IMPORT_RE.finditer(source):
            spec = m.group(1) or m.group(2) or m.group(3)
            if not spec or not spec.startswith("."):
                continue  # skip bare specifiers like 'react'
            # Resolve relative to f
            target = (f.parent / spec).resolve()
            # Try adding common extensions
            for ext in ("", ".ts", ".js", ".tsx", ".jsx", "/index.ts", "/index.js"):
                cand = Path(str(target) + ext)
                if cand.exists() and cand != f:
                    adj[f].add(cand)
                    break
    # Find cycles via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[Path, int] = {f: WHITE for f in files}
    cycles: list[list[Path]] = []
    path_stack: list[Path] = []

    def dfs(node: Path):
        color[node] = GRAY
        path_stack.append(node)
        for neighbor in adj.get(node, set()):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                # Cycle found — extract from path_stack
                idx = path_stack.index(neighbor)
                cycle = path_stack[idx:] + [neighbor]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        path_stack.pop()
        color[node] = BLACK

    for f in files:
        if color[f] == WHITE:
            dfs(f)
    # Deduplicate cycles by sorted tuple
    seen = set()
    for cycle in cycles:
        # Normalize: rotate so smallest file is first
        nodes_only = cycle[:-1]
        min_idx = nodes_only.index(min(nodes_only, key=str))
        rotated = nodes_only[min_idx:] + nodes_only[:min_idx]
        key = tuple(str(p) for p in rotated)
        if key in seen:
            continue
        seen.add(key)
        cycle_str = " -> ".join(p.name for p in cycle)
        findings.append(_finding(rotated[0], 1, "dependencies", "circular", "high",
            description=f"Circular dependency detected: {cycle_str}",
            evidence=[
                {"type": "tool_output", "tool": "polyglot-scan", "value": cycle_str},
                {"type": "file_list", "tool": "polyglot-scan", "value": ",".join(str(p) for p in rotated)},
            ], confidence=0.95, discriminator="|".join(key)))
    return findings


def scan_js_repo(root: Path) -> list[dict]:
    findings: list = []
    skip_dirs = {"node_modules", "dist", "build", ".git"}
    files = [p for p in list(root.rglob("*.ts")) + list(root.rglob("*.js")) + list(root.rglob("*.tsx")) + list(root.rglob("*.jsx"))
             if not any(part in skip_dirs for part in p.parts)]
    for f in files:
        findings.extend(scan_js_file(f))
    findings.extend(detect_js_cycles(root))
    return findings


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: polyglot_scan.py <rust|js> <path>"}))
        return 1
    lang = sys.argv[1]
    root = Path(sys.argv[2]).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 1
    if lang == "rust":
        findings = scan_rust_repo(root)
    elif lang in ("js", "ts", "javascript", "typescript"):
        findings = scan_js_repo(root)
    else:
        print(json.dumps({"error": f"unsupported language: {lang}"}))
        return 1
    print(json.dumps({"language": lang, "scanner": "polyglot-scan", "findings": findings}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
