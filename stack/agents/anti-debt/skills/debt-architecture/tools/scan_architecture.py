#!/usr/bin/env python3
"""
scan_architecture.py — Detect architecture-level technical debt.

Per ADR-0017 (Layer 3: Skills étendus) and V-max design Layer 3.
Outputs findings conforming to debt-finding.schema.json.
"""
from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
from finding_common import finding_id  # noqa: E402


# Architecture finding subcategories (per taxonomy/debt-categories.yaml extension V2)
ARCH_SUBCATEGORIES = {
    "circular_dependency",
    "high_coupling",
    "boundary_violation",
    "layer_leak",
    "god_module",
}


def detect_circular_imports_repo(repo_root: Path) -> list[list[str]]:
    """Detect circular imports across the entire Python repo.

    Edges keep the FULL dotted module name (not just the top-level package) so
    that cycles between nested-package modules (pkg.a <-> pkg.b) are detected,
    not only cycles between root-level modules. Imports that don't resolve to a
    repo module (stdlib, third-party) simply have no matching node and are
    ignored — they cannot create a false cycle.
    """
    py_files = list(repo_root.rglob("*.py"))
    if not py_files:
        return []

    # Build module name -> imports map
    module_imports: dict[str, set[str]] = {}
    for f in py_files:
        try:
            rel = f.relative_to(repo_root).with_suffix("").as_posix().replace("/", ".")
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)
            module_imports[rel] = imports
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue

    # DFS cycle detection
    cycles: list[list[str]] = []
    visited: set[str] = set()
    path_stack: list[str] = []
    path_set: set[str] = set()

    def dfs(node: str):
        path_stack.append(node)
        path_set.add(node)
        for nxt in module_imports.get(node, set()):
            if nxt in path_set:
                # Found a cycle
                cycle_start = path_stack.index(nxt)
                cycle = path_stack[cycle_start:] + [nxt]
                cycles.append(cycle)
            elif nxt not in visited:
                if nxt in module_imports:
                    dfs(nxt)
        path_stack.pop()
        path_set.discard(node)
        visited.add(node)

    for module in module_imports:
        if module not in visited:
            dfs(module)

    return cycles


def detect_high_coupling_python(repo_root: Path, threshold: int = 10) -> list[dict]:
    """Find modules with high fan-out (import many other modules)."""
    py_files = list(repo_root.rglob("*.py"))
    coupling_findings: list[dict] = []

    for f in py_files:
        try:
            rel = f.relative_to(repo_root).as_posix()
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module.split(".")[0])
            if len(imports) >= threshold:
                coupling_findings.append({
                    "file": rel,
                    "imports": sorted(imports),
                    "count": len(imports),
                })
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue

    return coupling_findings


def cycles_to_findings(
    cycles: list[list[str]],
    repo_root: Path,
) -> list[dict]:
    """Convert detected cycles to debt-finding format."""
    findings: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for cycle in cycles:
        cycle_str = " -> ".join(cycle)
        findings.append({
            "id": finding_id("architecture", "circular_dependency", cycle_str, "", cycle_str),
            "category": "architecture",
            "subcategory": "circular_dependency",
            "severity": "high",
            "location": {
                "file": " -> ".join(cycle),
                "symbol": "circular_import",
            },
            "description": f"Circular import detected: {cycle_str}",
            "evidence": [
                {
                    "type": "tool_output",
                    "tool": "scan_architecture",
                    "value": f"Cycle: {cycle_str}",
                },
            ],
            "confidence": 0.9,
            "source": "tool:custom",
            "estimated_effort": "M",
            "risk_of_fix": "high",
            "auto_fixable": False,
            "first_seen": now,
            "last_seen": now,
        })

    return findings


def coupling_to_findings(
    coupling: list[dict],
    threshold: int = 10,
) -> list[dict]:
    """Convert high-coupling modules to debt-finding format."""
    findings: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for c in coupling:
        if c["count"] >= threshold * 2:
            severity = "high"
        else:
            severity = "medium"

        findings.append({
            "id": finding_id("architecture", "high_coupling", c["file"], "", "high_fan_out"),
            "category": "architecture",
            "subcategory": "high_coupling",
            "severity": severity,
            "location": {
                "file": c["file"],
                "symbol": "high_fan_out",
            },
            "description": f"High coupling: {c['file']} imports {c['count']} modules (threshold: {threshold})",
            "evidence": [
                {
                    "type": "tool_output",
                    "tool": "scan_architecture",
                    "value": f"Imports: {', '.join(c['imports'][:20])}",
                },
            ],
            "confidence": 0.9,
            "source": "tool:custom",
            "estimated_effort": "L",
            "risk_of_fix": "medium",
            "auto_fixable": False,
            "first_seen": now,
            "last_seen": now,
        })

    return findings


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {root}"}))
        return 1

    # Only Python for now (V1.2 of this skill)
    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    has_python = pyproject.exists() or requirements.exists()
    if not has_python:
        # Check for any .py files anyway (best-effort)
        if not list(root.rglob("*.py")):
            print(json.dumps({"language": "none", "findings": [], "warning": "no Python project detected"}))
            return 0

    findings: list[dict] = []

    # 1. Circular imports
    cycles = detect_circular_imports_repo(root)
    findings.extend(cycles_to_findings(cycles, root))

    # 2. High coupling
    coupling = detect_high_coupling_python(root, threshold=10)
    findings.extend(coupling_to_findings(coupling, threshold=10))

    print(json.dumps({
        "language": "python",
        "scanner": "scan_architecture",
        "findings_count": len(findings),
        "findings": findings,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
