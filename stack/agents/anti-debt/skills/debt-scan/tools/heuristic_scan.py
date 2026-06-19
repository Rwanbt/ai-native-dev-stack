#!/usr/bin/env python3
"""heuristic_scan.py — Pure-Python fallback scanner (no external toolchain).

Extracted from scan_code.py to keep that orchestrator small. Detects hardcoded
secrets, long functions, unused imports, missing docstrings, duplication and
test-coverage gaps using only the stdlib `ast` + regex. Used when the language
linter (ruff/clippy/eslint) is unavailable, and for the always-on coverage check.

All findings carry a deterministic id (finding_common.finding_id) and conform to
debt-finding.schema.json.
"""
from __future__ import annotations

import ast
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id, SECRET_PATTERNS  # noqa: E402


def _finding_from_location(file: Path, line: int, category: str, subcategory: str,
                            severity: str, description: str, evidence_type: str,
                            evidence_value: str, tool: str = "python-ast",
                            discriminator: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": finding_id(category, subcategory, str(file), str(line), discriminator),
        "category": category,
        "subcategory": subcategory,
        "severity": severity,
        "location": {"file": str(file), "lines": f"{line}"},
        "description": description,
        "evidence": [
            {"type": "file_location", "value": f"{file}:{line}"},
            {"type": evidence_type, "tool": tool, "value": evidence_value},
        ],
        "confidence": 0.9,
        "source": f"tool:{tool}",
        "estimated_effort": "S",
        "risk_of_fix": "medium",
        "auto_fixable": False,
        "first_seen": now,
        "last_seen": now,
    }


def _project_has_strict_lint_config(root: Path) -> bool:
    """True if the project has a strict linter/typechecker configured.

    The missing-docs / dead-code heuristics only run in strict mode — without a
    linter configured they create noise on small/legacy projects.
    """
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            if any(s in content for s in ("tool.ruff", "tool.mypy", "tool.flake8",
                                            "tool.pylint", "[tool.black]")):
                return True
        except OSError:
            pass
    for cfg in (".flake8", "mypy.ini", ".pylintrc", "setup.cfg", "ruff.toml"):
        if (root / cfg).exists():
            return True
    return False


def _scan_secrets(py: Path, source: str) -> list[dict]:
    """One secrets_in_code finding per line that matches a secret pattern."""
    out = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(line):
                out.append(_finding_from_location(
                    file=py, line=lineno, category="security", subcategory="secrets_in_code",
                    severity="critical", description=f"Hardcoded {label}",
                    evidence_type="regex_match", evidence_value=line.strip()[:120],
                    tool="python-ast"))
                break  # one finding per line
    return out


def _scan_ast_smells(py: Path, tree: ast.AST, strict_mode: bool) -> tuple[list[dict], set]:
    """Long functions + (strict) missing docstrings. Also returns imported names."""
    out, imported = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_len = (node.end_lineno or node.lineno) - node.lineno + 1
            if func_len > 50:
                out.append(_finding_from_location(
                    file=py, line=node.lineno, category="code", subcategory="complexity",
                    severity="medium", description=f"Function '{node.name}' is {func_len} lines long",
                    evidence_type="ast_metric", evidence_value=f"function={node.name} lines={func_len}",
                    tool="python-ast"))
            if strict_mode and not node.name.startswith("_") and ast.get_docstring(node) is None:
                out.append(_finding_from_location(
                    file=py, line=node.lineno, category="code", subcategory="missing_docs",
                    severity="low", description=f"Public function '{node.name}' has no docstring",
                    evidence_type="ast_metric", evidence_value=f"function={node.name}",
                    tool="python-ast"))
    return out, imported


def _scan_dead_imports(py: Path, source: str, imported: set, strict_mode: bool) -> list[dict]:
    """Imports that appear in an import statement but are never referenced."""
    if not strict_mode:
        return []
    out = []
    for name in imported:
        total = len(re.compile(rf'\b{re.escape(name)}\b').findall(source))
        import_stmt_re = re.compile(
            rf'(?:^|\n)\s*(?:from\s+\S+\s+import\s+.*\b{re.escape(name)}\b|import\s+.*\b{re.escape(name)}\b)')
        import_occ = len(import_stmt_re.findall(source))
        if import_occ >= 1 and max(0, total - import_occ) == 0:
            out.append(_finding_from_location(
                file=py, line=1, category="code", subcategory="dead_code", severity="low",
                description=f"Import '{name}' appears unused", evidence_type="ast_metric",
                evidence_value=f"import={name} usage_count=0", tool="python-ast",
                discriminator=f"import={name}"))
    return out


def _hash_function_body(node: ast.AST) -> str:
    """Hash a function body ignoring docstrings, string constants and identifier
    names, so two functions with identical structure but different names match."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr):
        first = body[0]
        if isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            body = body[1:]

    class _NameStripper(ast.NodeTransformer):
        def visit_Constant(self, n):
            if isinstance(n.value, str):
                return ast.Constant(value="<STR>", kind=None)
            return n

        def visit_Name(self, n):
            return ast.Name(id="_", ctx=n.ctx)

        def visit_arg(self, n):
            return ast.arg(arg="_", annotation=None)

    body = _NameStripper().visit(ast.Module(body=body, type_ignores=[]))
    ast.fix_missing_locations(body)
    return hashlib.sha256(ast.dump(body).encode("utf-8")).hexdigest()[:16]


def _detect_python_duplication(py_files: list) -> list:
    """Find function bodies that appear duplicated (AST-hash match >= 2)."""
    by_hash: dict = {}
    for py in py_files:
        try:
            source = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            n_stmts = sum(1 for n in ast.walk(node) if isinstance(n, ast.stmt) and n is not node)
            if n_stmts < 2:
                continue
            h = _hash_function_body(node)
            by_hash.setdefault(h, []).append((py, node.lineno, node.name, n_stmts))
    findings: list = []
    for h, occurrences in by_hash.items():
        if len(occurrences) >= 2:
            files = sorted({str(o[0]) for o in occurrences})
            sample_py, sample_line, sample_name, _ = occurrences[0]
            findings.append(_finding_from_location(
                file=sample_py, line=sample_line, category="code", subcategory="duplication",
                severity="medium",
                description=f"Function body duplicated {len(occurrences)}x (hash {h}, first: '{sample_name}')",
                evidence_type="ast_hash",
                evidence_value=f"hash={h} occurrences={len(occurrences)} files={len(files)}",
                tool="python-ast", discriminator=h))
    return findings


def heuristic_python_scan(root: Path) -> list[dict]:
    """Pure-Python fallback scanner — no external tools required."""
    skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules", "build", "dist"}
    py_files = [p for p in root.rglob("*.py")
                if not any(part in skip_dirs for part in p.parts)]
    strict_mode = _project_has_strict_lint_config(root)

    findings: list[dict] = []
    for py in py_files:
        try:
            source = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings += _scan_secrets(py, source)
        try:
            tree = ast.parse(source, filename=str(py))
        except SyntaxError:
            continue
        ast_findings, imported = _scan_ast_smells(py, tree, strict_mode)
        findings += ast_findings
        findings += _scan_dead_imports(py, source, imported, strict_mode)
    findings += _detect_python_duplication(py_files)
    return findings


def detect_coverage_gaps(root: Path) -> list[dict]:
    """Detect missing or thin test coverage (no tests dir, or tests << sources)."""
    findings: list = []
    skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules", "build", "dist", ".tox", "tests"}
    src_files = [p for p in root.rglob("*.py") if not any(part in skip_dirs for part in p.parts)]
    test_files = []
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        test_files.extend(tests_dir.rglob("test_*.py"))
        test_files.extend(tests_dir.rglob("*_test.py"))
    test_files.extend(root.rglob("test_*.py"))
    test_files = [p for p in set(test_files) if "test" in p.name.lower()]

    if not test_files:
        anchor = root / "pyproject.toml" if (root / "pyproject.toml").exists() else root
        findings.append(_finding_from_location(
            file=anchor, line=1, category="tests", subcategory="coverage_gaps", severity="high",
            description="No test files found in project", evidence_type="filesystem_scan",
            evidence_value=f"src_files={len(src_files)} test_files=0", tool="python-ast"))
    elif len(src_files) > 5 and len(test_files) < len(src_files) / 3:
        findings.append(_finding_from_location(
            file=root, line=1, category="tests", subcategory="coverage_gaps", severity="medium",
            description=f"Thin test coverage: {len(test_files)} test files for {len(src_files)} source files",
            evidence_type="filesystem_scan",
            evidence_value=f"src_files={len(src_files)} test_files={len(test_files)} ratio={len(test_files)/max(len(src_files),1):.2f}",
            tool="python-ast"))
    return findings
