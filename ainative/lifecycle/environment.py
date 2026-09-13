"""What surrounds the project: the machine, the harness, the optional tools.

`doctor` used to answer for the lifecycle only: the install state and the
managed files. Everything that makes the product *work* — Git, a Python, the
harness hook entry, a configured vault, an optional graph — was invisible, so
"healthy" could be printed for a project whose automation could never fire.

Two rules shape this module.

*Optional is not failing.* A missing Node, Graphify or vault is
`ABSENT_OPTIONAL`: it removes a capability, not the product. `DEGRADED` is for
something configured-but-incomplete or a missing prerequisite of a claimed
profile; `FAIL` is reserved for what this install itself owns (the hook entry)
or for a requirement of the running CLI (Python).

*Every check states its impact.* "git: missing" is a fact a user cannot act on;
"without Git, Knowledge persistence and Verified provenance are unavailable" is
the same fact with its consequence, which is what the user needs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import hooks as hookslib

OK = "OK"
ABSENT_OPTIONAL = "ABSENT_OPTIONAL"
DEGRADED = "DEGRADED"
FAIL = "FAIL"

FAILING = (FAIL,)

# Where the global installer writes its per-harness entries. Read-only probes:
# doctor never writes to a user's home.
HARNESS_TARGETS = (
    (".claude/CLAUDE.md", "Claude Code"),
    (".codex/AGENTS.md", "Codex"),
    (".config/opencode/AGENTS.md", "OpenCode"),
    (".cursor/rules/ai-native-dev-stack.mdc", "Cursor"),
    (".gemini/GEMINI.md", "Gemini"),
    (".mavis/agents/mavis/agent.md", "Mavis"),
)

MACHINE_MANIFEST = Path(".ai-native") / "machine.json"


def _run(argv: list[str], cwd: Path | None = None, timeout: int = 10):
    try:
        return subprocess.run(argv, capture_output=True, text=True, cwd=cwd,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def git_root(project: Path) -> Path | None:
    result = _run(["git", "-C", str(project), "rev-parse", "--show-toplevel"])
    if result is None or result.returncode != 0:
        return None
    top = result.stdout.strip()
    return Path(top) if top else None


def git_info(project: Path) -> dict:
    available = shutil.which("git") is not None
    info = {"available": available, "repository": False, "root": None,
            "head": None, "dirty": None}
    if not available:
        return info
    root = git_root(project)
    if root is None:
        return info
    info["repository"] = True
    info["root"] = str(root)
    head = _run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"])
    if head is not None and head.returncode == 0:
        info["head"] = head.stdout.strip()
    status = _run(["git", "-C", str(root), "status", "--porcelain"])
    if status is not None and status.returncode == 0:
        info["dirty"] = bool(status.stdout.strip())
    return info


def _check(name: str, status: str, detail: str, impact: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "impact": impact}


def _python_check() -> dict:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 11):
        return _check("python", FAIL, f"Python {version}",
                      "the lifecycle CLI requires Python 3.11 or newer")
    return _check("python", OK, f"Python {version}")


def _git_check(info: dict) -> dict:
    if not info["available"]:
        return _check("git", DEGRADED, "git is not on PATH",
                      "Knowledge persistence and Verified provenance are unavailable")
    if not info["repository"]:
        return _check("git_repository", DEGRADED, "not inside a Git repository",
                      "Knowledge persistence and Verified provenance are unavailable; "
                      "run `git init` to enable them")
    detail = f"repository {info['root']}"
    if info["head"] is None:
        return _check("git_repository", DEGRADED, detail + " (no commit yet)",
                      "Work Plane provenance needs a committed HEAD")
    state = "dirty" if info["dirty"] else "clean"
    return _check("git_repository", OK, f"{detail}, HEAD {info['head'][:12]}, {state}")


def _node_check() -> dict:
    node = shutil.which("node")
    if node is None:
        return _check("node", ABSENT_OPTIONAL, "not installed",
                      "the session memory hooks need Node; the lifecycle does not")
    result = _run([node, "--version"])
    version = result.stdout.strip() if result is not None and result.returncode == 0 else "?"
    return _check("node", OK, f"Node {version}")


def _hook_check(project: Path) -> dict:
    report = hookslib.hook_status(project)
    status = report["status"]
    if status == hookslib.CONFIGURED:
        return _check("claude_hook", OK, "PostToolUse hook configured")
    impact = ("AI_SUMMARY.md is not regenerated after edits; run `ainative init` "
              "to (re)configure the hook")
    if status == hookslib.CONFIG_INVALID:
        return _check("claude_hook", FAIL, report["detail"],
                      "fix or remove .claude/settings.json, then run `ainative init`")
    return _check("claude_hook", FAIL, f"{status}: {report['detail']}", impact)


def _harness_check(home: Path) -> dict:
    found = [label for relative, label in HARNESS_TARGETS if (home / relative).is_file()]
    if not found:
        return _check("harness_integration", ABSENT_OPTIONAL, "no harness configured",
                      "machine-wide integration is separate: run "
                      "`python scripts/install_agents.py` from a stack checkout")
    return _check("harness_integration", OK, ", ".join(found))


def _vault_checks(project: Path, home: Path) -> list[dict]:
    checks: list[dict] = []
    vault = os.environ.get("OBSIDIAN_VAULT", "").strip()
    if not vault:
        checks.append(_check("vault", ABSENT_OPTIONAL, "OBSIDIAN_VAULT is not set",
                             "session memory load/save stays inactive"))
    else:
        root = Path(vault)
        registry = root / "_system" / "schemas" / "projects.json"
        if root.is_dir() and registry.is_file():
            checks.append(_check("vault", OK, str(root)))
        else:
            checks.append(_check("vault", DEGRADED,
                                 f"{root} is missing _system/schemas/projects.json",
                                 "the v4 contract cannot be verified; harness vault "
                                 "blocks stay inactive"))
    url = os.environ.get("OBSIDIAN_API_URL", "").strip()
    if not url:
        checks.append(_check("obsidian_api", ABSENT_OPTIONAL, "OBSIDIAN_API_URL is not set"))
    elif not _is_loopback(url):
        checks.append(_check("obsidian_api", DEGRADED, f"non-loopback URL refused: {url}",
                             "only the local Obsidian REST API is supported"))
    else:
        reachable = _probe_loopback(url)
        checks.append(_check("obsidian_api", OK if reachable else DEGRADED,
                             f"{url} {'reachable' if reachable else 'unreachable'}",
                             "" if reachable else "the session hooks will report their save as failed"))
    return checks


def _is_loopback(url: str) -> bool:
    return any(marker in url for marker in ("127.0.0.1", "localhost", "[::1]"))


def _probe_loopback(url: str) -> bool:
    request = urllib.request.Request(url.rstrip("/") + "/", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status < 500
    except Exception:
        return False


def _graphify_check(project: Path) -> dict:
    configured = os.environ.get("GRAPHIFY_BIN", "").strip()
    graph = project / "graphify-out" / "graph.json"
    if configured and Path(configured).is_file():
        return _check("graphify", OK, configured)
    if graph.is_file():
        return _check("graphify", OK, str(graph))
    return _check("graphify", ABSENT_OPTIONAL, "not installed",
                  "dependency-path context in the assembler stays unavailable")


def _machine_check(home: Path) -> dict:
    manifest = home / MACHINE_MANIFEST
    if manifest.is_file():
        return _check("machine_integration", OK, str(manifest))
    return _check("machine_integration", ABSENT_OPTIONAL, "no machine manifest",
                  "run `python scripts/install_agents.py` from a stack checkout")


def _workplane_check(project: Path) -> dict:
    anchor = project / ".ai-native" / "trust" / "project_trust.json"
    if anchor.is_file():
        return _check("work_plane_trust", OK, "trust anchor present")
    return _check("work_plane_trust", DEGRADED, "no trust anchor",
                  "Work Contracts are ungoverned until `ainative trust init` and "
                  "`ainative trust bootstrap` run")


def environment_checks(project: Path, *, installed: bool = False,
                       home: Path | None = None, verified: bool = False) -> list[dict]:
    """Every check `doctor` reports beside the lifecycle diagnosis."""

    project = Path(project).resolve()
    home = Path(home) if home is not None else Path.home()
    info = git_info(project)
    checks = [_python_check(), _git_check(info), _node_check()]
    if installed:
        checks.append(_hook_check(project))
    checks.append(_harness_check(home))
    checks.extend(_vault_checks(project, home))
    checks.append(_graphify_check(project))
    checks.append(_machine_check(home))
    if verified:
        checks.append(_workplane_check(project))
    return checks


def failing(checks: list[dict]) -> list[dict]:
    return [check for check in checks if check["status"] in FAILING]


__all__ = ["OK", "ABSENT_OPTIONAL", "DEGRADED", "FAIL", "environment_checks",
           "failing", "git_root", "git_info", "HARNESS_TARGETS", "MACHINE_MANIFEST"]