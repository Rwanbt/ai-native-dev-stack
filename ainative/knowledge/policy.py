"""Promotion approval policy: who may change which canonical target.

Conservative by default (plan Phase K4 gate, ADR-0011 section 5): every
canonical target requires an explicit human approval statement TODAY.
The per-class table exists so a LATER ADR can relax one class on
evaluation evidence — relaxing means editing this table plus its ADR,
never a silent flag. AI_CONTEXT auto-promotion stays forbidden: there
is no non-human path through this module at all. Approval is recorded
as its own audit event BEFORE the patch applies, so a promotion always
shows who approved what base.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import KnowledgeError

AGENTS = "AGENTS.md"
KFP = "KNOWN_FAILURE_PATTERNS.md"
AI_CONTEXT = "AI_CONTEXT.md"
ADR = "ADR"
OTHER = "OTHER"

RULES = {
    AGENTS: {"human_approval": True,
             "reason": "project-wide rules affect every agent session"},
    KFP: {"human_approval": True,
          "reason": "failure patterns become shared diagnosis truth"},
    AI_CONTEXT: {"human_approval": True,
                 "reason": "module invariants gate retrieval; auto-promotion "
                           "forbidden until evaluation evidence (ADR-0011)"},
    ADR: {"human_approval": True,
          "reason": "architecture decisions are permanent history"},
}


def classify_target(project: Path, dest: Path) -> str:
    """One policy class for a resolved target. Defense in depth."""

    try:
        relative = dest.resolve().relative_to(Path(project).resolve()).as_posix()
    except ValueError:
        return OTHER
    name = dest.name
    if name == "AGENTS.md":
        return AGENTS
    if name in ("KNOWN_FAILURE_PATTERNS.md", "KNOWN_FAILURE_PATTERNS"):
        return KFP
    if name == "AI_CONTEXT.md":
        return AI_CONTEXT
    if relative.startswith("docs/adr/"):
        return ADR
    return OTHER


def check(project: Path, candidate: dict, dest: Path, *,
          actor: str, approve: str | None) -> dict[str, Any]:
    """Enforce the rule, or refuse. Returns the approval record."""

    target_class = classify_target(project, dest)
    if target_class == OTHER:
        raise KnowledgeError("KNOWLEDGE_TARGET_UNSUPPORTED",
                             f"promotion to {dest.name!r} is outside the "
                             "approved target classes",
                             target_class=target_class)
    rule = RULES[target_class]
    if rule["human_approval"] and not approve:
        raise KnowledgeError("KNOWLEDGE_APPROVAL_REQUIRED",
                             f"promoting to {target_class} needs a human: "
                             f"re-run with --approve \"<reason>\" ({rule['reason']})",
                             target_class=target_class)
    return {"target_class": target_class, "by": actor,
            "statement": approve or "", "rule": rule["reason"]}


__all__ = ["AGENTS", "KFP", "AI_CONTEXT", "ADR", "OTHER", "RULES",
           "classify_target", "check"]