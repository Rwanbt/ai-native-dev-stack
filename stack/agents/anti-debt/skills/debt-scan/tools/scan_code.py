#!/usr/bin/env python3
"""scan_code.py — Orchestrate static code scanners per language.

Detects the primary language of the repo and runs the appropriate linter.
Normalizes the output into the debt-finding schema.

Usage:
    python3 scan_code.py [path-to-repo]

Output: JSON array of debt-finding objects on stdout.
Exits with 0 on success, 1 on missing language / scanner.
"""
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id  # noqa: E402


LANG_MAP = [
    # (marker_file, language, scanner_command, json_parser)
    ("pyproject.toml", "python", "ruff check --output-format=json", "ruff"),
    ("requirements.txt", "python", "ruff check --output-format=json", "ruff"),
    # B3 fix: clippy --no-deps avoids requiring a full debug build
    ("Cargo.toml", "rust", "cargo clippy --no-deps --message-format=json --quiet", "clippy"),
    ("package.json", "typescript", "npx --no-install eslint --format=json .", "eslint"),
    ("tsconfig.json", "typescript", "npx --no-install eslint --format=json .", "eslint"),
    ("go.mod", "go", "golangci-lint run --out-format=json", "golangci-lint"),
    ("pom.xml", "java", "mvn -q spotbugs:spotbugs", "spotbugs"),
    ("build.gradle", "java", "gradle spotbugsMain", "spotbugs"),
]


def detect_language(root: Path) -> tuple[str, str, str] | None:
    """Return (language, scanner_command, parser) or None.

    B2 fix: if no marker file, fall back to heuristic language detection
    by counting source files. Always prefers a marker file when present.
    """
    for marker, lang, cmd, parser in LANG_MAP:
        if (root / marker).exists():
            return lang, cmd, parser
    # Heuristic fallback: count file extensions
    py_count = sum(1 for _ in root.rglob("*.py"))
    rs_count = sum(1 for _ in root.rglob("*.rs"))
    ts_count = sum(1 for _ in root.rglob("*.ts")) + sum(1 for _ in root.rglob("*.tsx"))
    counts = [("python", py_count, ("pyproject.toml", "python", "ruff check --output-format=json", "ruff")),
              ("rust", rs_count, ("Cargo.toml", "rust", "cargo clippy --no-deps --message-format=json --quiet", "clippy")),
              ("typescript", ts_count, ("tsconfig.json", "typescript", "npx --no-install eslint --format=json .", "eslint"))]
    counts.sort(key=lambda c: c[1], reverse=True)
    if counts[0][1] > 0:
        # We treat as if the marker existed, so the LANG_MAP path is reused
        # by passing the heuristic-found command directly
        return counts[0][2][1], counts[0][2][2], counts[0][2][3]
    return None


def normalize_ruff(stdout: str, root: Path) -> list[dict]:
    """Convert ruff JSON output to debt-finding schema."""
    findings = []
    try:
        raw = json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError:
        return findings

    now = datetime.now(timezone.utc).isoformat()

    # ruff code -> subcategory mapping (best-effort V1)
    SUBCAT_MAP = {
        "F401": ("code", "dead_code", "low"),  # imported but unused
        "F841": ("code", "dead_code", "low"),  # local variable assigned but unused
        "E501": ("code", "complexity", "low"),  # line too long
        "C901": ("code", "complexity", "medium"),  # too complex
        "B105": ("security", "weak_crypto", "high"),  # hardcoded password
        "B106": ("security", "weak_crypto", "high"),  # hardcoded password (function arg)
        "B107": ("security", "weak_crypto", "medium"),  # hardcoded password default
        "S301": ("security", "unsafe_io", "high"),  # pickle
        "S324": ("security", "weak_crypto", "high"),  # insecure hash
        "S501": ("security", "auth_issues", "high"),  # request without timeout
    }

    for item in raw:
        code = item.get("code", "")
        # Convention: ruff code like "F401" -> subcategory
        sub = SUBCAT_MAP.get(code, ("code", "complexity", "low"))
        _row = f"{item.get('location', {}).get('row', '?')}"
        finding = {
            "id": finding_id(sub[0], sub[1], item.get("filename", ""), _row, code),
            "category": sub[0],
            "subcategory": sub[1],
            "severity": sub[2],
            "location": {
                "file": item.get("filename", ""),
                "lines": _row,
                "symbol": item.get("name", ""),
            },
            "description": f"{code}: {item.get('message', '')}",
            "evidence": [
                {
                    "type": "file_location",
                    "value": f"{item.get('filename', '')}:{item.get('location', {}).get('row', '?')}",
                },
                {
                    "type": "tool_output",
                    "tool": "ruff",
                    "value": f"{code} at {item.get('filename', '')}:{item.get('location', {}).get('row', '?')}",
                },
            ],
            "confidence": 1.0,
            "source": "tool:ruff",
            "estimated_effort": "S",
            "risk_of_fix": "low",
            "auto_fixable": item.get("fix") is not None,
            "first_seen": now,
            "last_seen": now,
        }
        findings.append(finding)
    return findings


def normalize_clippy(stdout: str, root: Path) -> list[dict]:
    """Convert cargo clippy JSON output to debt-finding schema."""
    findings = []
    now = datetime.now(timezone.utc).isoformat()

    # Clippy emits one JSON object per line
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if item.get("reason") != "compiler-message":
            continue

        message = item.get("message", {})
        code = message.get("code", {})
        if code is None:
            continue

        code_str = code.get("code", "")
        spans = message.get("spans", [])
        primary_span = next((s for s in spans if s.get("is_primary")), spans[0] if spans else None)
        if not primary_span:
            continue

        _cfile = str(primary_span.get("file_name", ""))
        _cline = f"{primary_span.get('line_start', {}).get('line_start', '?')}"
        finding = {
            "id": finding_id("code", "complexity", _cfile, _cline, code_str),
            "category": "code",
            "subcategory": "complexity",
            "severity": "medium",
            "location": {
                "file": _cfile,
                "lines": _cline,
            },
            "description": f"{code_str}: {message.get('message', '')}",
            "evidence": [
                {
                    "type": "file_location",
                    "value": f"{primary_span.get('file_name', '')}:{primary_span.get('line_start', {}).get('line_start', '?')}",
                },
                {
                    "type": "tool_output",
                    "tool": "clippy",
                    "value": f"{code_str}",
                },
            ],
            "confidence": 1.0,
            "source": "tool:clippy",
            "estimated_effort": "S",
            "risk_of_fix": "low",
            "auto_fixable": False,
            "first_seen": now,
            "last_seen": now,
        }
        findings.append(finding)
    return findings


PARSERS = {
    "ruff": normalize_ruff,
    "clippy": normalize_clippy,
    # V2: add eslint, golangci-lint, spotbugs
}


def run_scanner(root: Path, cmd: str, parser: str) -> list[dict]:
    """Run the scanner command and return normalized findings."""
    # B1 fix: explicit binary check (Windows + shell=True does not raise
    # FileNotFoundError when the binary is missing — it just returns 1).
    binary = cmd.split()[0] if isinstance(cmd, str) else cmd[0]
    if binary not in ("npx",) and shutil.which(binary) is None:
        return [{
            "warning": f"scanner binary not found: {binary}",
            "recommendation": f"install {binary} to enable {parser} support",
        }]
    try:
        result = subprocess.run(
            cmd.split() if isinstance(cmd, str) else cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(root),
            timeout=300,
            shell=isinstance(cmd, str) and (" " in cmd),
        )
        # ruff + clippy return nonzero when issues found — that's OK
        if result.returncode not in (0, 1):
            return [{
                "warning": f"scanner exited with code {result.returncode}",
                "stderr_tail": (result.stderr or "")[-500:],
            }]
        normalize = PARSERS.get(parser)
        if normalize is None:
            return [{"warning": f"no parser for {parser}"}]
        return normalize(result.stdout, root)
    except subprocess.TimeoutExpired:
        return [{"warning": f"scanner timed out after 300s"}]
    except FileNotFoundError as e:
        return [{
            "warning": f"scanner binary not found: {e.filename}",
            "recommendation": f"install the scanner to enable {parser} support",
        }]
    except Exception as e:
        return [{"warning": f"scanner failed: {type(e).__name__}: {e}"}]


# B1 fix: heuristic Python AST-based scan — used when ruff is not installed
# so the result is not silently empty. Best-effort: secrets (regex), long
# functions, dead imports, missing docstrings on public functions.

SECRET_PATTERNS = [
    (re.compile(r'sk_live_[A-Za-z0-9]{20,}'), "Stripe live secret key"),
    (re.compile(r'sk_test_[A-Za-z0-9]{20,}'), "Stripe test secret key"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS access key ID"),
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), "Google API key"),
    (re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}'), "GitHub token"),
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), "Slack token"),
    (re.compile(r'-----BEGIN [A-Z ]+PRIVATE KEY-----'), "Private key"),
    # Generic high-entropy credential assigned to a secret-named variable.
    # Catches hardcoded secrets that aren't a known provider format (checked
    # last, so provider-specific labels win for real keys).
    (re.compile(r'(?i)(?:api[_-]?key|secret|token|passwd|password|access[_-]?key|client[_-]?secret)\s*[:=]\s*["\'][A-Za-z0-9+/_\-]{16,}["\']'), "generic credential"),
]


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
        "location": {
            "file": str(file),
            "lines": f"{line}",
        },
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
    """Return True if the project has a strict linter/typechecker configured.

    These heuristics (missing docstrings, unused imports) are only useful when
    the project has a linter that would also flag them. Without config, they
    create noise on small/legacy projects.
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


def heuristic_python_scan(root: Path) -> list[dict]:
    """Pure-Python fallback scanner — no external tools required.

    Detects hardcoded secrets, long functions, unused imports, missing docstrings
    and duplication. `missing_docs`/`dead_code` are only emitted in strict mode
    (a linter configured) to avoid noise on small/legacy projects.
    """
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


def _hash_function_body(node: ast.AST) -> str:
    """Hash a function body ignoring docstrings, string constants, and identifier names.

    Two functions with identical structure but different variable/argument names
    (e.g. parse_user_data vs process_record) should hash to the same value.
    """
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
                file=sample_py, line=sample_line,
                category="code", subcategory="duplication",
                severity="medium",
                description=f"Function body duplicated {len(occurrences)}x (hash {h}, first: '{sample_name}')",
                evidence_type="ast_hash",
                evidence_value=f"hash={h} occurrences={len(occurrences)} files={len(files)}",
                tool="python-ast",
                discriminator=h,
            ))
    return findings


def detect_coverage_gaps(root: Path) -> list[dict]:
    """Detect missing or thin test coverage.

    Heuristics:
    - No tests/ directory or test_*.py files at all → high severity
    - Source has N .py files but tests have < N/3 → medium severity
    """
    findings: list = []
    skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules", "build", "dist", ".tox", "tests"}
    src_files = [p for p in root.rglob("*.py") if not any(part in skip_dirs for part in p.parts)]
    test_files = []
    # Look for tests/ directory
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        test_files.extend(tests_dir.rglob("test_*.py"))
        test_files.extend(tests_dir.rglob("*_test.py"))
    # Also look for any test_*.py at the root or in subdirs
    test_files.extend(root.rglob("test_*.py"))
    test_files = list(set(test_files))
    test_files = [p for p in test_files if "test" in p.name.lower()]

    if not test_files:
        anchor = root / "pyproject.toml" if (root / "pyproject.toml").exists() else root
        findings.append(_finding_from_location(
            file=anchor, line=1,
            category="tests", subcategory="coverage_gaps",
            severity="high",
            description="No test files found in project",
            evidence_type="filesystem_scan",
            evidence_value=f"src_files={len(src_files)} test_files=0",
            tool="python-ast",
        ))
    elif len(src_files) > 5 and len(test_files) < len(src_files) / 3:
        findings.append(_finding_from_location(
            file=root, line=1,
            category="tests", subcategory="coverage_gaps",
            severity="medium",
            description=f"Thin test coverage: {len(test_files)} test files for {len(src_files)} source files",
            evidence_type="filesystem_scan",
            evidence_value=f"src_files={len(src_files)} test_files={len(test_files)} ratio={len(test_files)/max(len(src_files),1):.2f}",
            tool="python-ast",
        ))
    return findings


def _augment_python(root: Path, findings: list) -> list:
    """Add the AST heuristic fallback (if the linter was missing) + coverage gaps."""
    # B1 fix: if the only result is "scanner binary not found", fall back to the
    # pure-Python AST heuristic so the result is not silently empty.
    if (findings and isinstance(findings[0], dict) and "warning" in findings[0]
            and "not found" in findings[0].get("warning", "")):
        findings = heuristic_python_scan(root) + detect_coverage_gaps(root) + findings
    # Always add coverage gaps (orthogonal concern), avoiding duplicates.
    existing = {f.get("subcategory") for f in findings if isinstance(f, dict)}
    for cf in detect_coverage_gaps(root):
        if cf.get("subcategory") not in existing:
            findings.insert(0, cf)
    return findings


def _augment_polyglot(root: Path, lang: str, findings: list) -> list:
    """Always also run the toolchain-free polyglot scanner for Rust/JS/TS."""
    polyglot_bin = Path(__file__).parent.parent.parent.parent / "tools" / "polyglot_scan.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(polyglot_bin), "rust" if lang == "rust" else "js", str(root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        if proc.stdout.strip():
            return json.loads(proc.stdout).get("findings", []) + findings
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        pass
    return findings


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 1
    detected = detect_language(root)
    if not detected:
        print(json.dumps({"error": "no_supported_language", "path": str(root)}))
        return 1
    lang, cmd, parser = detected
    findings = run_scanner(root, cmd, parser)
    if lang == "python":
        findings = _augment_python(root, findings)
    elif lang in ("rust", "typescript"):
        findings = _augment_polyglot(root, lang, findings)
    print(json.dumps({"language": lang, "scanner": parser, "findings": findings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
