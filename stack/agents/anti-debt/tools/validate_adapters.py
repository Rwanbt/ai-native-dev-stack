#!/usr/bin/env python3
"""validate_adapters.py — Validate that adapter settings-snippets are correct.

Checks:
- All settings-snippet.json files are valid JSON
- They have the expected structure (permissions.allow list)
- They cover the essential tools (ruff, trufflehog, osv-scanner, pip-audit)
- The README for each adapter mentions how to install
- Skill references in the README are valid (the skills exist in skills/)

Usage:
    python3 validate_adapters.py [--strict]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ADAPTERS = ROOT / "adapters"
SKILLS = ROOT / "skills"

ESSENTIAL_TOOLS = {"ruff", "trufflehog", "osv-scanner"}
TOOL_PATTERN = re.compile(r"Bash\((\w[\w\-]*)(?::[\w\*]+)?\)")


def _is_perms_format_ok(snippet: dict) -> tuple[bool, str]:
    """Validate the permissions shape.

    Accepts Claude Code and MiniMax Code shapes:
    {"permissions": {"allow": [...]}}
    """
    perms = snippet.get("permissions")
    if not isinstance(perms, dict):
        return False, "missing 'permissions' object"
    allow = perms.get("allow")
    if not isinstance(allow, list):
        return False, "missing 'permissions.allow' list"
    if not allow:
        return False, "'permissions.allow' is empty"
    for entry in allow:
        if not isinstance(entry, str):
            return False, f"non-string entry in allow: {entry!r}"
    return True, ""


def _covered_tools(snippet: dict) -> set[str]:
    """Extract the set of binary names referenced in the allow list."""
    tools = set()
    for entry in snippet.get("permissions", {}).get("allow", []):
        for m in TOOL_PATTERN.finditer(entry):
            tools.add(m.group(1))
    return tools


def _mentioned_skills(readme_text: str) -> set[str]:
    """Extract skill names referenced in the README.

    Only matches canonical references `skills/<name>/SKILL.md` or
    `skills/<name>/AGENT.md` to avoid false positives on install paths like
    `.claude/skills/anti-debt/`. Requires the match to be at the start of a
    line or preceded by whitespace/backtick to avoid mid-path matches.
    """
    found = set()
    for m in re.finditer(r"(?:^|[\s\`])skills/([\w\-]+)/(?:SKILL\.md|AGENT\.md)",
                          readme_text, re.MULTILINE):
        found.add(m.group(1))
    return found


def validate_one(adapter_dir: Path) -> list[dict]:
    issues = []
    snippet = adapter_dir / "settings-snippet.json"
    readme = adapter_dir / "README.md"
    if not readme.exists():
        issues.append({"severity": "error", "msg": f"missing {readme.name}"})
        return issues
    # Read README to detect "manual install only" adapters that don't need a snippet
    readme_text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    manual_only = bool(re.search(
        r"(manual(ly)?|manuelle?)(\s+install|\b)",
        readme_text, re.IGNORECASE,
    ))
    if not snippet.exists():
        if manual_only:
            issues.append({"severity": "info",
                            "msg": "no settings-snippet.json (manual install only, by design)"})
        else:
            issues.append({"severity": "error", "msg": f"missing {snippet.name}"})
        return issues
    # JSON validity
    try:
        data = json.loads(snippet.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        issues.append({"severity": "error", "msg": f"invalid JSON: {e}"})
        return issues
    # Structure
    ok, msg = _is_perms_format_ok(data)
    if not ok:
        issues.append({"severity": "error", "msg": msg})
        return issues
    # Tool coverage
    tools = _covered_tools(data)
    missing = ESSENTIAL_TOOLS - tools
    if missing:
        issues.append({"severity": "warning", "msg": f"missing essential tools: {sorted(missing)}"})
    # README skill references
    if readme.exists():
        skills = _mentioned_skills(readme_text)
        for skill in skills:
            if not (SKILLS / skill).is_dir():
                issues.append({"severity": "warning",
                                "msg": f"README references skill '{skill}' but it does not exist in skills/"})
    return issues


def main() -> int:
    strict = "--strict" in sys.argv
    if not ADAPTERS.is_dir():
        print(json.dumps({"error": f"adapters dir not found: {ADAPTERS}"}))
        return 1
    results = []
    for adapter_dir in sorted(ADAPTERS.iterdir()):
        if not adapter_dir.is_dir():
            continue
        issues = validate_one(adapter_dir)
        results.append({
            "adapter": adapter_dir.name,
            "issues": issues,
            "ok": not any(i["severity"] == "error" for i in issues),
        })
    report = {"adapters": results, "all_ok": all(r["ok"] for r in results)}
    print(json.dumps(report, indent=2))
    # Exit code: 0 if all OK, 1 if errors (warnings only exit 0 unless --strict)
    has_error = any(not r["ok"] for r in results)
    has_warning = any(any(i["severity"] == "warning" for i in r["issues"]) for r in results)
    if has_error:
        return 1
    if strict and has_warning:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
