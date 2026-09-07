"""Staleness: which promoted knowledge a change may have invalidated.

A canonical fact goes stale when its target file, its evidence paths
or its graph neighborhood moves. This module never rewrites canonical
files: it reports findings (`POTENTIALLY_STALE` is a signal, not a
candidate state) and, with `--apply`, raises PENDING review candidates
carrying GIT_HISTORY evidence — one per impacted promotion, deduplicated
so repeated scans never spam the store. The code-to-knowledge bridge is
derived on demand from candidates plus promotion audits: deleting it
loses nothing, rebuilding it costs one scan.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ainative.lifecycle import state as statelib

from . import dedupe as dedupelib
from . import evidence as evidencelib
from . import store as storelib
from .candidate import MAX_CLAIM_CHARS, TERMINAL, validate_locator
from .dedupe import normalize
from .errors import KnowledgeError

POTENTIALLY_STALE = "POTENTIALLY_STALE"
REVIEW_PREFIX = "Re-verify (potentially stale): "
GRAPH_RADIUS = 2


def _promote_audits(project: Path, candidate_id: str) -> list[dict]:
    return [event for event in storelib.read_audit(project)
            if event.get("candidate_id") == candidate_id
            and event.get("operation") == "PROMOTE"]


def _refs(candidate: dict, audits: list[dict]) -> dict[str, list[str]]:
    targets = [str(event["detail"].get("target", "")) for event in audits
               if event.get("detail", {}).get("target")]
    locators = [str(item.get("locator", "")) for item in candidate.get("evidence", [])
                if item.get("locator")]
    return {"targets": targets, "locators": locators}


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def impacted(project: Path, changed: list[str],
             *, graph: Any | None = None) -> list[dict[str, Any]]:
    """Promoted candidates a change may invalidate. Read-only."""

    normalized = [validate_locator(path).replace("\\", "/") for path in changed]
    adjacent: dict[str, dict[str, Any]] = {}
    if graph is not None:
        try:
            for path in normalized:
                for neighbor in graph.neighbors(path, max_neighbors=20):
                    if neighbor.distance <= GRAPH_RADIUS:
                        known = adjacent.get(neighbor.path)
                        if known is None or neighbor.distance < known["distance"]:
                            adjacent[neighbor.path] = {"via": path,
                                                       "distance": neighbor.distance}
        except Exception:
            adjacent = {}
    findings = []
    for candidate in storelib.read_all(Path(project)):
        if candidate["status"] != "PROMOTED":
            continue
        refs = _refs(candidate, _promote_audits(Path(project), candidate["candidate_id"]))
        signals = []
        for path in normalized:
            if path in refs["targets"]:
                signals.append({"changed": path, "signal": "target-modified"})
            if path in refs["locators"]:
                signals.append({"changed": path, "signal": "evidence-path-modified"})
            for known in refs["targets"] + refs["locators"]:
                if known and _basename(known) == _basename(path) and known != path:
                    signals.append({"changed": path, "signal": "possibly-relocated",
                                    "was": known})
            for known in refs["targets"] + refs["locators"]:
                hit = adjacent.get(known)
                if hit is not None:
                    signals.append({"changed": hit["via"], "signal": "graph-adjacent",
                                    "distance": hit["distance"], "ref": known})
        if signals:
            findings.append({"candidate_id": candidate["candidate_id"],
                             "claim": candidate["claim"], "kind": candidate["kind"],
                             "state": POTENTIALLY_STALE, "signals": signals})
    return findings


def raise_reviews(project: Path, findings: list[dict[str, Any]], *,
                  actor: str = "unknown") -> dict[str, list[str]]:
    """Persist one PENDING review candidate per finding. Skips existing."""

    from .candidate import capture as capture_candidate

    created, skipped = [], []
    try:
        known = {normalize(item["claim"]) for item in storelib.read_all(Path(project))
                 if item["status"] not in TERMINAL}
    except KnowledgeError:
        known = set()
    for finding in findings:
        original = storelib.inspect_candidate(Path(project), finding["candidate_id"])
        budget = MAX_CLAIM_CHARS - len(REVIEW_PREFIX)
        claim = REVIEW_PREFIX + original["claim"][:budget]
        if normalize(claim) in known:
            skipped.append(finding["candidate_id"])
            continue
        stored = storelib.append(Path(project), capture_candidate(
            project=str(original["provenance"].get("project", project)),
            agent=actor, session=statelib.new_identifier("scan"),
            origin_type="staleness_signal", kind=original["kind"], claim=claim,
            module=original["scope"].get("module"),
            source_paths=tuple(signal["changed"] for signal in finding["signals"])))
        for signal in finding["signals"]:
            evidencelib.add_evidence(
                Path(project), stored["candidate_id"],
                {"type": "GIT_HISTORY", "locator": signal["changed"]}, actor=actor)
        storelib.record_audit(Path(project), candidate_id=stored["candidate_id"],
                              operation="STALENESS_REVIEW",
                              detail={"parent": finding["candidate_id"],
                                      "signals": finding["signals"]},
                              actor=actor)
        known.add(normalize(claim))
        created.append(stored["candidate_id"])
    return {"created": created, "skipped": skipped}


def bridge(project: Path) -> dict[str, Any]:
    """Code-to-knowledge registry, derived on demand. Deletable, rebuildable."""

    knowledge, code_index = [], {}
    for candidate in storelib.read_all(Path(project)):
        refs = _refs(candidate, _promote_audits(Path(project), candidate["candidate_id"]))
        paths = sorted({path for path in refs["targets"] + refs["locators"] if path})
        knowledge.append({"candidate_id": candidate["candidate_id"],
                          "status": candidate["status"], "kind": candidate["kind"],
                          "module": candidate["scope"].get("module"),
                          "paths": paths})
        for path in paths:
            code_index.setdefault(path, []).append(candidate["candidate_id"])
    return {"knowledge": knowledge, "code_index": code_index}


def git_changed(project: Path, *, timeout: int = 10) -> tuple[list[str], str | None]:
    """Tracked modifications plus deletions. Best-effort, never raises."""

    try:
        status = subprocess.run(["git", "-C", str(project), "status", "--porcelain"],
                                capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return [], "git unavailable"
    if status.returncode != 0:
        return [], "not a git checkout"
    changed = []
    for line in status.stdout.splitlines():
        if len(line) < 4 or line.startswith("??"):
            continue
        changed.append(line[3:].strip().strip('"'))
    try:
        diff = subprocess.run(["git", "-C", str(project), "diff", "--name-only", "HEAD"],
                              capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        diff = None
    if diff is not None and diff.returncode == 0:
        changed += [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    return sorted(set(changed)), None


__all__ = ["POTENTIALLY_STALE", "REVIEW_PREFIX", "GRAPH_RADIUS", "impacted",
           "raise_reviews", "bridge", "git_changed"]