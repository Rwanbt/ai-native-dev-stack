#!/usr/bin/env python3
"""scan_deps.py — Audit dependencies (vulnerabilities, obsoleteness, circular).

Detects the package manager in use and runs the appropriate audit.
Also runs dependency-cruiser if available (circular deps in JS/TS).

Usage:
    python3 scan_deps.py [path-to-repo]
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id  # noqa: E402


DEPENDENCY_TOOLS = [
    {
        "name": "cargo-audit",
        "marker": "Cargo.toml",
        "cmd": ["cargo", "audit", "--json"],
        "installed_check": ["cargo", "audit", "--version"],
        "category": "security",
        "subcategory": "known_vulns",
    },
    {
        "name": "pip-audit",
        "marker": "requirements.txt",
        "cmd": ["pip-audit", "--format", "json", "-r", "requirements.txt"],
        "installed_check": ["pip-audit", "--version"],
        "category": "security",
        "subcategory": "known_vulns",
    },
    {
        "name": "npm-audit",
        "marker": "package.json",
        "cmd": ["npm", "audit", "--json"],
        "installed_check": ["npm", "--version"],
        "category": "security",
        "subcategory": "known_vulns",
    },
    {
        "name": "dependency-cruiser",
        "marker": "package.json",
        "cmd": ["depcruise", "--output-type", "json", "."],
        "installed_check": ["depcruise", "--version"],
        "category": "dependencies",
        "subcategory": "circular",
        "circular_only": True,  # Only emit findings on circular errors
    },
]


def is_installed(check_cmd: list[str]) -> bool:
    try:
        result = subprocess.run(check_cmd, capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def parse_cargo_audit(stdout: str) -> list[dict]:
    """Convert cargo audit JSON to debt-finding schema."""
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return findings

    vulns = data.get("vulnerabilities", {}).get("found", [])
    for v in vulns:
        advisory = v.get("advisory", {})
        package = v.get("package", "?")
        version = v.get("package_version", "?")
        advisory_id = advisory.get("id", "?")
        title = advisory.get("title", "")
        # Cargo audit severity is in advisory database
        severity = "high"  # Default for known vulns

        findings.append({
            "id": finding_id("security", "known_vulns", "Cargo.toml", "",
                             f"{package}@{version}:{advisory_id}"),
            "category": "security",
            "subcategory": "known_vulns",
            "severity": severity,
            "location": {"file": "Cargo.toml", "symbol": f"{package}@{version}"},
            "description": f"RUSTSEC-{advisory_id}: {title[:200]}",
            "evidence": [
                {"type": "tool_output", "tool": "cargo-audit", "value": f"{package}@{version} has RUSTSEC-{advisory_id}"},
            ],
            "confidence": 1.0,
            "source": "tool:cargo-audit",
            "estimated_effort": "M",
            "risk_of_fix": "medium",
            "auto_fixable": False,
            "first_seen": now,
            "last_seen": now,
        })
    return findings


def parse_pip_audit(stdout: str) -> list[dict]:
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return findings

    dependencies = data.get("dependencies", [])
    for dep in dependencies:
        vulns = dep.get("vulns", [])
        for v in vulns:
            fix_versions = v.get("fix_versions", [])
            findings.append({
                "id": finding_id("security", "known_vulns", "requirements.txt", "",
                                 f"{dep.get('name', '?')}:{v.get('id', '?')}"),
                "category": "security",
                "subcategory": "known_vulns",
                "severity": "high",
                "location": {"file": "requirements.txt", "symbol": dep.get("name", "?")},
                "description": f"{v.get('id', '?')}: {v.get('description', '')[:200]}",
                "evidence": [
                    {"type": "tool_output", "tool": "pip-audit", "value": f"{dep.get('name', '?')} vulnerable to {v.get('id', '?')}"},
                ],
                "confidence": 1.0,
                "source": "tool:pip-audit",
                "estimated_effort": "S" if fix_versions else "M",
                "risk_of_fix": "low" if fix_versions else "medium",
                "auto_fixable": bool(fix_versions),
                "first_seen": now,
                "last_seen": now,
            })
    return findings


def parse_npm_audit(stdout: str) -> list[dict]:
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return findings

    vulnerabilities = data.get("vulnerabilities", {})
    for pkg_name, advisory in vulnerabilities.items():
        if isinstance(advisory, dict) and "severity" in advisory:
            severity = advisory.get("severity", "high")
            via = advisory.get("via", [])
            title = via[0].get("title", "") if via and isinstance(via[0], dict) else ""

            findings.append({
                "id": finding_id("security", "known_vulns", "package.json", "", pkg_name),
                "category": "security",
                "subcategory": "known_vulns",
                "severity": severity,
                "location": {"file": "package.json", "symbol": pkg_name},
                "description": f"{pkg_name}: {title[:200]}",
                "evidence": [
                    {"type": "tool_output", "tool": "npm-audit", "value": f"{pkg_name} has {severity} vulnerability"},
                ],
                "confidence": 1.0,
                "source": "tool:npm-audit",
                "estimated_effort": "S",
                "risk_of_fix": "low",
                "auto_fixable": True,
                "first_seen": now,
                "last_seen": now,
            })
    return findings


def parse_dependency_cruiser(stdout: str) -> list[dict]:
    """Convert depcruise output. Only emit on circular errors (other issues = noise)."""
    findings = []
    now = datetime.now(timezone.utc).isoformat()
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return findings

    for err in data.get("errors", []):
        if err.get("type") == "cycle":
            cycle = " -> ".join(err.get("cycle", []))
            findings.append({
                "id": finding_id("dependencies", "circular", "package.json", "", cycle),
                "category": "dependencies",
                "subcategory": "circular",
                "severity": "high",
                "location": {"file": "package.json"},
                "description": f"Circular dependency detected: {cycle}",
                "evidence": [
                    {"type": "tool_output", "tool": "dependency-cruiser", "value": f"Cycle: {cycle}"},
                ],
                "confidence": 1.0,
                "source": "tool:dependency-cruiser",
                "estimated_effort": "L",
                "risk_of_fix": "high",
                "auto_fixable": False,
                "first_seen": now,
                "last_seen": now,
            })
    return findings


PARSERS = {
    "cargo-audit": parse_cargo_audit,
    "pip-audit": parse_pip_audit,
    "npm-audit": parse_npm_audit,
    "dependency-cruiser": parse_dependency_cruiser,
}


# --- Heuristic fallback: detect known-outdated packages when no audit tool ---
# This is a MINIMAL fallback. Real vulnerability detection requires
# pip-audit / cargo-audit / npm-audit. This is best-effort.
KNOWN_OUTDATED = {
    "requests": "2.20.0",   # CVE-2018-18074
    "django": "2.2.0",      # Multiple historic CVEs
    "flask": "0.12.0",      # CVE-2018-1000656
    "pyyaml": "5.1",        # CVE-2017-18342
    "pillow": "7.0.0",      # Multiple CVEs
    "urllib3": "1.24.0",    # CVE-2019-9740 / CVE-2019-9947
    "jinja2": "2.11.0",     # CVE-2019-10906
    "cryptography": "2.7",  # CVE-2020-25659
    "paramiko": "2.7.1",    # CVE-2022-24302
    "pyjwt": "1.7.1",       # CVE-2022-29217
    "pyopenssl": "19.0.0",  # CVE-2019-9631
    "sqlalchemy": "1.3.0",  # Multiple CVEs
}


def _parse_version(v: str) -> tuple:
    """Parse a version string like '2.20.0' or '>=1.0' into comparable tuple."""
    v = v.strip().lstrip(">=").lstrip("<=").lstrip("==").lstrip(">").lstrip("<").strip()
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            # Take numeric prefix
            num = ""
            for c in p:
                if c.isdigit():
                    num += c
                else:
                    break
            parts.append(int(num) if num else 0)
    return tuple(parts[:3])


def heuristic_python_deps(root: Path) -> list[dict]:
    """Detect outdated Python deps by parsing requirements.txt.

    Used when pip-audit is not installed. Confidence is set low (0.5) to
    reflect heuristic nature — findings go to the 'review' tier.
    """
    findings: list = []
    req = root / "requirements.txt"
    if not req.exists():
        return findings
    now = datetime.now(timezone.utc).isoformat()
    try:
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Parse "package==version" or "package>=version" etc.
            if "==" in line:
                name, ver = line.split("==", 1)
            elif ">=" in line:
                name, ver = line.split(">=", 1)
            elif "<=" in line:
                name, ver = line.split("<=", 1)
            elif ">" in line:
                name, ver = line.split(">", 1)
            elif "<" in line:
                name, ver = line.split("<", 1)
            else:
                continue
            name = name.strip().lower()
            ver = ver.split(";")[0].split("#")[0].strip()
            if name in KNOWN_OUTDATED:
                if _parse_version(ver) < _parse_version(KNOWN_OUTDATED[name]):
                    findings.append({
                        "id": finding_id("security", "known_vulns", "requirements.txt", "",
                                         f"outdated:{name}"),
                        "category": "security",
                        "subcategory": "known_vulns",
                        "severity": "high",
                        "location": {"file": "requirements.txt", "symbol": f"{name}=={ver}"},
                        "description": f"{name}=={ver} is older than known-fixed version {KNOWN_OUTDATED[name]} (heuristic, verify with pip-audit)",
                        "evidence": [
                            {"type": "tool_output", "tool": "heuristic", "value": f"{name}=={ver} < {KNOWN_OUTDATED[name]}"},
                        ],
                        "confidence": 0.5,  # Heuristic — requires human review
                        "source": "tool:python-deps-heuristic",
                        "estimated_effort": "S",
                        "risk_of_fix": "low",
                        "auto_fixable": True,
                        "first_seen": now,
                        "last_seen": now,
                    })
    except OSError:
        pass
    return findings


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 1

    all_findings = []
    installed_tools = []
    warnings = []

    for tool in DEPENDENCY_TOOLS:
        if not (root / tool["marker"]).exists():
            continue
        if not is_installed(tool["installed_check"]):
            warnings.append({
                "warning": f"tool:{tool['name']} not installed (skipped)",
                "recommendation": f"install {tool['name']} for {tool['marker']} projects",
            })
            continue

        installed_tools.append(tool["name"])
        try:
            result = subprocess.run(
                tool["cmd"],
                capture_output=True,
                text=True,
                cwd=str(root),
                timeout=600,
            )
            # audit tools exit nonzero on issues found — that's expected
            findings = PARSERS[tool["name"]](result.stdout)
            all_findings.extend(findings)
        except subprocess.TimeoutExpired:
            warnings.append({"warning": f"{tool['name']} timed out"})
        except Exception as e:
            warnings.append({"warning": f"{tool['name']} failed: {type(e).__name__}: {e}"})

    # Heuristic fallback for Python: detect outdated packages when pip-audit
    # is not installed. Findings are tagged confidence=0.5 to land in 'review' tier.
    if (root / "requirements.txt").exists() and "pip-audit" not in installed_tools:
        heuristic_findings = heuristic_python_deps(root)
        all_findings.extend(heuristic_findings)
        if heuristic_findings:
            warnings.append({
                "warning": "used python-deps heuristic (pip-audit not installed)",
                "recommendation": "install pip-audit for authoritative CVE detection",
                "findings_count": len(heuristic_findings),
            })

    print(json.dumps({
        "tools_installed": installed_tools,
        "tools_skipped": warnings,
        "findings": all_findings,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
