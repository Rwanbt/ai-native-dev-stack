"""Control paths: Local Payload ignored, Project Audit tracked (B1 S2-S3).

Before any persistence, both directions are enforced mechanically
against Git: the state tree MUST be ignored, the audit tree MUST NOT
be. Outside a Git work tree there is nothing to stage, so the check
reports `unchecked` instead of refusing — the enforced configurations
(inside Git) are covered by tests. Failure is
CONTROL_PATH_POLICY_INVALID with the remedy, never a silent write.
Store directories are additionally checked for symlink/junction escape
with the shared lifecycle primitive before every mutation batch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ainative.lifecycle import paths as pathslib

from .errors import KnowledgeError

STATE_DIRNAME = Path(".ai-native") / "state" / "knowledge"
AUDIT_DIRNAME = Path(".ai-native") / "audit" / "knowledge"


def state_dir(project: Path) -> Path:
    return Path(project) / STATE_DIRNAME


def audit_dir(project: Path) -> Path:
    return Path(project) / AUDIT_DIRNAME


def _git(*args: str, timeout: int = 10):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _work_tree(project: Path) -> Path | None:
    result = _git("-C", str(project), "rev-parse", "--show-toplevel")
    if result is None or result.returncode != 0:
        return None
    top = result.stdout.strip()
    return Path(top) if top else None


def _is_ignored(work_tree: Path, path: Path) -> bool | None:
    """True/False via check-ignore; None when Git cannot answer."""

    try:
        relative = path.resolve().relative_to(work_tree.resolve()).as_posix()
    except ValueError:
        return False
    result = _git("-C", str(work_tree), "check-ignore", "-q", relative)
    if result is None or result.returncode not in (0, 1):
        return None
    return result.returncode == 0


def ensure_policy(project: Path) -> dict[str, Any]:
    """Inspect the bidirectional ignore policy. Diagnostic only."""

    root = Path(project)
    work_tree = _work_tree(root)
    if work_tree is None:
        return {"enforced": False, "reason": "not inside a Git repository"}
    state_ignored = _is_ignored(work_tree, state_dir(root))
    audit_ignored = _is_ignored(work_tree, audit_dir(root))
    if state_ignored is None or audit_ignored is None:
        return {"enforced": False, "reason": "git check-ignore unavailable"}
    return {"enforced": True, "state_ignored": state_ignored,
            "audit_ignored": audit_ignored}


def require_policy(project: Path) -> dict[str, Any]:
    """Gate every persistence on positively verified policy. Fail closed.

    Three outcomes, no silent fallback: outside a Git repository, or an
    unverifiable policy, refuses CONTROL_PATH_POLICY_INVALID; only a
    positively verified configuration allows the write. A non-Git local
    mode would be an explicitly separate mode, never this fallback.
    """

    root = Path(project)
    report = ensure_policy(root)
    if report["enforced"] is not True:
        raise KnowledgeError("KNOWLEDGE_CONTROL_PATH_POLICY_INVALID",
                             f"control path policy unverified ({report['reason']}); "
                             "refusing write")
    if report["state_ignored"] is not True:
        raise KnowledgeError("KNOWLEDGE_CONTROL_PATH_POLICY_INVALID",
                             f"{STATE_DIRNAME.as_posix()} MUST be Git-ignored; "
                             "refusing Local Control write")
    if report["audit_ignored"] is not False:
        raise KnowledgeError("KNOWLEDGE_CONTROL_PATH_POLICY_INVALID",
                             f"{AUDIT_DIRNAME.as_posix()} MUST NOT be Git-ignored; "
                             "refusing audit write")
    return report


def _no_planted_link(root: Path, directory: Path) -> None:
    """Refuse before creating anything: a planted link must not gain targets."""

    try:
        relative = directory.relative_to(root)
    except ValueError:
        raise KnowledgeError("KNOWLEDGE_CONTROL_PATH_POLICY_INVALID",
                             f"store directory escapes the project: {directory}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            try:
                current.resolve().relative_to(root.resolve())
            except ValueError:
                raise KnowledgeError("KNOWLEDGE_CONTROL_PATH_POLICY_INVALID",
                                     f"store link escapes the project: {current}")


def ensure_contained(project: Path) -> None:
    """Refuse symlink/junction escape of the store trees. Fail closed."""

    root = Path(project)
    for directory in (state_dir(root), audit_dir(root)):
        _no_planted_link(root, directory)
        directory.mkdir(parents=True, exist_ok=True)
        if not pathslib.is_within(root, directory):
            raise KnowledgeError("KNOWLEDGE_CONTROL_PATH_POLICY_INVALID",
                                 f"store directory escapes the project: {directory}")


__all__ = ["STATE_DIRNAME", "AUDIT_DIRNAME", "state_dir", "audit_dir",
           "ensure_policy", "require_policy", "ensure_contained"]
