#!/usr/bin/env python3
"""static_analysis.py — Layer 1: Advanced static analysis for Python projects.

Computes per-function metrics that the simple ruff/AST scanner cannot:
- Cyclomatic complexity (CC) — number of decision points
- Cognitive complexity — adds nesting penalty
- Function size (lines, statements)
- Duplication detection — AST-hash of function bodies
- Caller / callee map (callgraph)
- Fan-in / fan-out per module

Output: JSON array of findings following the debt-finding schema.
Usage:
    python3 static_analysis.py [path-to-repo]
"""
from __future__ import annotations
import ast
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finding_common import finding_id  # noqa: E402

# --- Thresholds (tunable in `scoring-calibration.md` V1.2) ---
CC_THRESHOLD = 10         # > 10 = high complexity
CC_CRITICAL = 20          # > 20 = critical
FUNC_LINES_WARN = 50      # > 50 lines = medium
FUNC_LINES_HIGH = 100     # > 100 lines = high
DUP_MIN_AST_SIZE = 2      # ignore trivially small functions from duplication
FANOUT_HIGH = 20          # module with > 20 imports = high coupling
NESTING_HIGH = 4          # > 4 levels deep = high


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding(file: Path, line: int, category: str, subcategory: str, severity: str,
              description: str, evidence: list, confidence: float = 0.95,
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
        "source": "tool:static-analysis",
        "estimated_effort": "S",
        "risk_of_fix": "medium",
        "auto_fixable": False,
        "first_seen": _now(),
        "last_seen": _now(),
    }


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Count decision points + 1.

    Standard cyclomatic complexity: +1 for each branching construct.
    """
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            cc += 1
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            cc += 1
        elif isinstance(child, (ast.While,)):
            cc += 1
        elif isinstance(child, ast.ExceptHandler):
            cc += 1
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            # and/or chains add len(values)-1
            cc += len(child.values) - 1
        elif isinstance(child, (ast.Match,)):
            # each case is a branch
            cc += len(child.cases)
        elif isinstance(child, ast.Assert):
            cc += 1
        elif isinstance(child, ast.comprehension):
            cc += 1
    return cc


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    """Return max nesting depth of loops/ifs/with inside the node."""
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                              ast.IfExp, ast.Match)):
            d = _max_nesting(child, depth + 1)
        else:
            d = _max_nesting(child, depth)
        if d > max_d:
            max_d = d
    return max_d


def _function_signature(node: ast.AST) -> str:
    """Compact string representation of a function signature for hashing."""
    args = []
    if hasattr(node, "args"):
        for a in node.args.args:
            args.append(a.arg)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        for a in node.args.kwonlyargs:
            args.append(a.arg)
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
    return f"{type(node).__name__}({','.join(args)})"


def analyze_file(path: Path) -> tuple[list, list]:  # CC-EXCEPTION: see ADR-0025 (sequential AST parser)
    """Analyze a single Python file.

    Returns (findings, function_records) where function_records is a list of
    dicts {file, name, line, cc, size, ast_hash, callees}.
    """
    findings: list = []
    records: list = []

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings, records

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return findings, records

    # 1. Per-function metrics
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cc = _cyclomatic_complexity(node)
        n_lines = (node.end_lineno or node.lineno) - node.lineno + 1
        n_statements = sum(1 for n in ast.walk(node)
                           if isinstance(n, ast.stmt) and n is not node)
        nesting = _max_nesting(node)
        # callees (function calls inside)
        callees = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                if isinstance(sub.func, ast.Name):
                    callees.add(sub.func.id)
                elif isinstance(sub.func, ast.Attribute):
                    callees.add(sub.func.attr)
        # AST hash (deduplicate functions that are literal copies).
        # Strip the docstring (first statement if it's a constant string) and
        # all literal string values, so two functions with different docstrings
        # but identical logic hash to the same value.
        body_for_hash = list(node.body)
        if body_for_hash and isinstance(body_for_hash[0], ast.Expr):
            first = body_for_hash[0]
            if isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                body_for_hash = body_for_hash[1:]
        # Replace all string constants with a placeholder to ignore log/error messages
        class _StringStripper(ast.NodeTransformer):
            def visit_Constant(self, node):
                if isinstance(node.value, str):
                    return ast.Constant(value="<STR>", kind=None)
                return node
        body_for_hash = _StringStripper().visit(ast.Module(body=body_for_hash, type_ignores=[]))
        ast.fix_missing_locations(body_for_hash)
        body_dumped = ast.dump(body_for_hash)
        ast_hash = hashlib.sha256(body_dumped.encode("utf-8")).hexdigest()[:16]

        sig = _function_signature(node)
        records.append({
            "file": str(path),
            "name": node.name,
            "line": node.lineno,
            "cc": cc,
            "lines": n_lines,
            "statements": n_statements,
            "nesting": nesting,
            "ast_hash": ast_hash,
            "sig": sig,
            "callees": sorted(callees),
        })

        # CC thresholds — subcategory "complexity" (matches test corpus expectations)
        if cc >= CC_CRITICAL:
            findings.append(_finding(path, node.lineno, "code", "complexity", "high",
                description=f"Function '{node.name}' has cyclomatic complexity {cc} (>= {CC_CRITICAL})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{node.lineno}"},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"function={node.name} cc={cc}"},
                ]))
        elif cc >= CC_THRESHOLD:
            findings.append(_finding(path, node.lineno, "code", "complexity", "medium",
                description=f"Function '{node.name}' has cyclomatic complexity {cc} (>= {CC_THRESHOLD})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{node.lineno}"},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"function={node.name} cc={cc}"},
                ]))

        # Length
        if n_lines >= FUNC_LINES_HIGH:
            findings.append(_finding(path, node.lineno, "code", "long_function", "high",
                description=f"Function '{node.name}' is {n_lines} lines long (>= {FUNC_LINES_HIGH})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{node.lineno}"},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"function={node.name} lines={n_lines}"},
                ]))
        elif n_lines >= FUNC_LINES_WARN:
            findings.append(_finding(path, node.lineno, "code", "long_function", "medium",
                description=f"Function '{node.name}' is {n_lines} lines long (>= {FUNC_LINES_WARN})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{node.lineno}"},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"function={node.name} lines={n_lines}"},
                ]))

        # Deep nesting
        if nesting > NESTING_HIGH:
            findings.append(_finding(path, node.lineno, "code", "deep_nesting", "medium",
                description=f"Function '{node.name}' has nesting depth {nesting} (>{NESTING_HIGH})",
                evidence=[
                    {"type": "file_location", "value": f"{path}:{node.lineno}"},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"function={node.name} nesting={nesting}"},
                ], confidence=0.85))

    # 2. Module-level fan-out
    imports = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports += 1
    if imports > FANOUT_HIGH:
        findings.append(_finding(path, 1, "code", "high_coupling", "medium",
            description=f"Module imports {imports} external/internal modules (>{FANOUT_HIGH})",
            evidence=[
                {"type": "file_location", "value": f"{path}:1"},
                {"type": "ast_metric", "tool": "static-analysis", "value": f"module={path.name} fanout={imports}"},
            ], confidence=0.9))

    return findings, records


def detect_duplication(records: list, threshold: int = 2) -> list:
    """Find functions with identical AST hashes appearing >= threshold times."""
    by_hash: dict = defaultdict(list)
    for rec in records:
        body_size = rec["statements"]
        if body_size < DUP_MIN_AST_SIZE:
            continue
        by_hash[rec["ast_hash"]].append(rec)
    findings: list = []
    for h, recs in by_hash.items():
        if len(recs) >= threshold:
            # group by file to avoid spamming
            files = sorted({r["file"] for r in recs})
            sample_file = Path(recs[0]["file"])
            findings.append(_finding(sample_file, recs[0]["line"], "code", "duplication", "medium",
                description=f"Function body duplicated {len(recs)}x across {len(files)} files (AST hash {h})",
                evidence=[
                    {"type": "ast_hash", "tool": "static-analysis", "value": h},
                    {"type": "file_list", "tool": "static-analysis", "value": ",".join(files)},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"duplications={len(recs)} files={len(files)}"},
                ], confidence=0.95, discriminator=h))
    return findings


def analyze_repo(root: Path) -> dict:
    """Analyze a Python repository. Returns {findings, stats}."""
    skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules", "build", "dist", ".tox"}
    py_files = [p for p in root.rglob("*.py") if not any(part in skip_dirs for part in p.parts)]
    all_findings: list = []
    all_records: list = []
    for py in py_files:
        f, r = analyze_file(py)
        all_findings.extend(f)
        all_records.extend(r)
    dup_findings = detect_duplication(all_records)
    all_findings.extend(dup_findings)
    # God-class detection: a function that is very long AND has many branches
    for rec in all_records:
        if rec["lines"] > 40 and rec["cc"] > 12:
            fpath = Path(rec["file"])
            all_findings.append(_finding(fpath, rec["line"], "code", "god_classes", "medium",
                description=f"Function '{rec['name']}' is a god function: {rec['lines']} lines, CC={rec['cc']}",
                evidence=[
                    {"type": "file_location", "value": f"{fpath}:{rec['line']}"},
                    {"type": "ast_metric", "tool": "static-analysis", "value": f"function={rec['name']} lines={rec['lines']} cc={rec['cc']}"},
                ]))
    return {
        "findings": all_findings,
        "stats": {
            "files_scanned": len(py_files),
            "functions_analyzed": len(all_records),
            "complexity_findings": sum(1 for f in all_findings if f["subcategory"] == "complexity"),
            "long_function_findings": sum(1 for f in all_findings if f["subcategory"] == "long_function"),
            "duplication_findings": len(dup_findings),
            "coupling_findings": sum(1 for f in all_findings if f["subcategory"] == "high_coupling"),
            "god_class_findings": sum(1 for f in all_findings if f["subcategory"] == "god_classes"),
        },
    }


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 1
    result = analyze_repo(root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
