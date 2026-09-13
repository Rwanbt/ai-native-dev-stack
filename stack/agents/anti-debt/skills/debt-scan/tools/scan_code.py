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
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id  # noqa: E402
from heuristic_scan import heuristic_python_scan, detect_coverage_gaps  # noqa: E402


LANG_MAP = [
    # (marker_file, language, scanner_argv, json_parser)
    # Native argument vectors, never shell strings: see run_scanner (#127).
    ("pyproject.toml", "python", ("ruff", "check", "--output-format=json"), "ruff"),
    ("requirements.txt", "python", ("ruff", "check", "--output-format=json"), "ruff"),
    # B3 fix: clippy --no-deps avoids requiring a full debug build
    ("Cargo.toml", "rust",
     ("cargo", "clippy", "--no-deps", "--message-format=json", "--quiet"), "clippy"),
    ("package.json", "typescript",
     ("npx", "--no-install", "eslint", "--format=json", "."), "eslint"),
    ("tsconfig.json", "typescript",
     ("npx", "--no-install", "eslint", "--format=json", "."), "eslint"),
    ("go.mod", "go", ("golangci-lint", "run", "--out-format=json"), "golangci-lint"),
    ("pom.xml", "java", ("mvn", "-q", "spotbugs:spotbugs"), "spotbugs"),
    ("build.gradle", "java", ("gradle", "spotbugsMain"), "spotbugs"),
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
    counts = [("python", py_count, ("pyproject.toml", "python", ("ruff", "check", "--output-format=json"), "ruff")),
              ("rust", rs_count, ("Cargo.toml", "rust", ("cargo", "clippy", "--no-deps", "--message-format=json", "--quiet"), "clippy")),
              ("typescript", ts_count, ("tsconfig.json", "typescript", ("npx", "--no-install", "eslint", "--format=json", "."), "eslint"))]
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
        # Clippy emits line_start as an integer; reading it as a mapping
        # raised AttributeError, which the broad except then swallowed into a
        # warning - so every clippy finding silently degraded (#127).
        _line_start = primary_span.get("line_start")
        _cline = str(_line_start) if isinstance(_line_start, int) else "?"
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
                    "value": f"{_cfile}:{_cline}",
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


WINDOWS_SHIM_SUFFIXES = (".cmd", ".bat")


def executable_argv(argv, *, platform_name: str | None = None,
                    which=None) -> list[str]:
    """The process argv for a scanner, never routed through a shell string.

    Windows cannot hand a `.cmd`/`.bat` shim (npx, mvn, gradle) to
    CreateProcess, so exactly those are invoked through `cmd /c` with the
    resolved path. Every original argument stays a separate argv element, so
    nothing is ever re-parsed by a shell (#127). Everywhere else the argv is
    returned unchanged.
    """

    argv = [str(item) for item in argv]
    if (platform_name or os.name) == "nt":
        resolve = which or shutil.which
        resolved = resolve(argv[0]) or argv[0]
        if resolved.lower().endswith(WINDOWS_SHIM_SUFFIXES):
            return ["cmd", "/c", resolved, *argv[1:]]
    return argv


def run_scanner(root: Path, argv, parser: str) -> list[dict]:
    """Run the scanner and return normalized findings.

    `argv` is a native argument vector and the process is spawned with
    `shell=False` (#127): splitting a string and handing it to a shell was both
    an injection surface and wrong for any path containing a space. The Windows
    shim exception above keeps the vector intact.
    """

    argv = tuple(str(item) for item in argv)
    # B1 fix: explicit binary check — a missing binary must degrade loudly
    # rather than produce a confusing exit code from the spawn itself.
    binary = argv[0]
    if binary not in ("npx",) and shutil.which(binary) is None:
        return [{
            "warning": f"scanner binary not found: {binary}",
            "recommendation": f"install {binary} to enable {parser} support",
        }]
    try:
        result = subprocess.run(
            executable_argv(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(root),
            timeout=300,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return [{"warning": "scanner timed out after 300s"}]
    except OSError as error:
        return [{
            "warning": f"scanner could not run: {error}",
            "recommendation": f"install the scanner to enable {parser} support",
        }]
    # ruff + clippy return nonzero when issues found — that's OK
    if result.returncode not in (0, 1):
        return [{
            "warning": f"scanner exited with code {result.returncode}",
            "stderr_tail": (result.stderr or "")[-500:],
        }]
    normalize = PARSERS.get(parser)
    if normalize is None:
        return [{"warning": f"no parser for {parser}"}]
    # Deliberately unguarded: a parser defect (the clippy line_start
    # AttributeError of #127) must surface as a failed scan, not as a
    # per-scanner warning that reads like a missing tool.
    return normalize(result.stdout, root)


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
    lang, argv, parser = detected
    findings = run_scanner(root, argv, parser)
    if lang == "python":
        findings = _augment_python(root, findings)
    elif lang in ("rust", "typescript"):
        findings = _augment_polyglot(root, lang, findings)
    print(json.dumps({"language": lang, "scanner": parser, "findings": findings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
