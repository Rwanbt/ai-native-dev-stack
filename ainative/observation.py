"""Locally observed forge facts: remotes, and what they support.

Read-only by construction: the only subprocess is `git remote`, the only inputs
are the pure resolver, the install state and the claim journal. No network, no
credentials, no writes, no persistent trust (PR-3, #164). Diagnostic only — an
ambiguity is rendered, never resolved by preference.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import claims
from . import forge as forgelib
from .lifecycle import environment
from .lifecycle import features as featureslib
from .lifecycle import manifest as manifestlib
from .lifecycle import state as statelib
from .lifecycle.errors import LifecycleError

RESOLVED = "RESOLVED"
AMBIGUOUS = "AMBIGUOUS"
UNAVAILABLE = "UNAVAILABLE"
MISMATCH = "MISMATCH"

_RESOLUTION_STATES = {
    "WORK_AUTHORITY_AMBIGUOUS": AMBIGUOUS,
    "WORK_AUTHORITY_UNAVAILABLE": UNAVAILABLE,
    "WORK_AUTHORITY_MISMATCH": MISMATCH,
}


def read_remotes(project: Path) -> tuple[forgelib.ObservedRemote, ...]:
    """The project's Git remotes, or () when there are none / it is not a repo."""

    names = _git(project, "remote")
    if not names:
        return ()
    remotes = []
    for name in names.splitlines():
        name = name.strip()
        if not name:
            continue
        url = _git(project, "remote", "get-url", name)
        if url:
            remotes.append(forgelib.ObservedRemote(name=name, url=url.strip()))
    return tuple(remotes)


def _git(project: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(["git", "-C", str(project), *arguments],
                                   capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def forge_picture(project: Path, *, explicit=None, declared=None) -> dict:
    """Observed remotes plus the resolver's answer, as a renderable state."""

    observed = read_remotes(project)
    record = {"git": environment.git_root(project) is not None,
              "remotes": [remote.to_record() for remote in observed],
              "resolution": {"state": UNAVAILABLE, "authority": None, "detail": ""}}
    try:
        authority = forgelib.resolve_observed_work_authority(
            explicit=explicit, declared=declared, remotes=observed)
    except LifecycleError as refusal:
        record["resolution"]["state"] = _RESOLUTION_STATES.get(refusal.code, UNAVAILABLE)
        record["resolution"]["detail"] = refusal.message
        return record
    record["resolution"] = {"state": RESOLVED, "authority": authority.to_record(),
                            "detail": ""}
    return record


def project_view(project: Path) -> dict:
    """What `forge status` and doctor display: features, forge, claim attempts."""

    distribution = manifestlib.load()
    effective = featureslib.project_install_state(statelib.load(project), distribution)
    return {
        "features": {"active": list(effective.active_features) if effective else [],
                     "projected_from_legacy": bool(
                         effective and effective.projected_from_legacy),
                     "legacy_default": featureslib.legacy_default(distribution)},
        "forge": forge_picture(project),
        "claim_attempts": _claim_summary(project),
    }


def doctor_lines(view: dict) -> list[str]:
    """The doctor extension as text lines (PR-3 / #164). Never a credential."""

    features = view["features"]
    resolution = view["forge"]["resolution"]
    authority = resolution.get("authority") or {}
    summary = view["claim_attempts"]
    lines = [
        "Features",
        "  active: " + (", ".join(features["active"]) or "none")
        + ("  (projected from the V1 state)" if features["projected_from_legacy"] else ""),
        "Work authority (observed)",
        "  state: " + resolution["state"]
        + (f"  {authority.get('provider')}:{authority.get('project')}" if authority else ""),
    ]
    for remote in view["forge"]["remotes"]:
        lines.append(f"  {remote['name']:<10} {remote['provider']:<8} "
                     f"{remote['project'] or '-'}")
    if features["projected_from_legacy"] and any(
            remote["provider"] == "gitlab" for remote in view["forge"]["remotes"]):
        # A legacy project with a GitLab remote keeps the compatibility default
        # until it says otherwise; the switch is explicit, never inferred from
        # the remote (ADR-0017 section 4 / scenario M).
        lines.append("  note: a GitLab remote is observed while the legacy "
                     f"{features.get('legacy_default', 'forge-github')} default is "
                     "projected; run `ainative feature switch forge-gitlab` to "
                     "switch explicitly")
    if summary["journal"] == "ok":
        lines.append(f"Claim attempts: {len(summary['unresolved'])} unresolved")
    else:
        lines.append(f"Claim attempts: journal unavailable ({summary['detail']})")
    return lines


def _claim_summary(project: Path) -> dict:
    try:
        pending = [attempt.to_record() for attempt in claims.unresolved(project)]
    except LifecycleError as error:
        # An unreadable journal is a fact to display, not a crash: doctor must
        # keep diagnosing the rest, and the refusal is visible in the output.
        return {"journal": "unavailable", "unresolved": [], "detail": error.message}
    return {"journal": "ok", "unresolved": pending, "detail": ""}


__all__ = ["RESOLVED", "AMBIGUOUS", "UNAVAILABLE", "MISMATCH",
           "read_remotes", "forge_picture", "project_view", "doctor_lines"]
