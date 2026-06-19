#!/usr/bin/env python3
"""scan_code.py — Orchestrate static code scanners per language.

Detects the primary language of the repo and runs the appropriate linter.
Normalizes the output into the debt-finding schema.

Usage:
    python3 scan_code.py [path-to-repo]

Output: JSON array of debt-finding objects on stdout.
Exits with 0 on success, 1 on missing language / scanner.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id  # noqa: E402
from heuristic_scan import heuristic_python_scan, detect_coverage_gaps  # noqa: E402


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
