"""Observe the provenance a checkout can actually establish.

Evidence and approval roots carry a provenance string. On its own that string
proves only that someone wrote it: an artifact claiming SIGNED is not a
signature, and one claiming GIT_REVIEWED is not a review. This module observes
the repository and reports the highest level it can establish by itself, and
the evaluator caps every declared level at what was observed.

What a local checkout can establish:

    LOCAL_UNTRUSTED   no usable Git checkout, or the state cannot be observed
    GIT_DIRTY         a checkout exists and the observed paths are modified
    GIT_RECORDED      the observed paths are tracked and match the commit
    SIGNED            the head commit's signature verifies

GIT_REVIEWED and CI_APPROVED are deliberately not observable here. They assert
that a *process* happened, which a checkout cannot show, and this build ships
no attestation verifier. A policy demanding either therefore cannot be
satisfied — which is the fail-closed answer, not a gap to paper over.
"""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from pathlib import Path
from typing import Iterable

from .trust import TRUST_LEVELS

# The levels this module is able to establish on its own.
OBSERVABLE = ("LOCAL_UNTRUSTED", "GIT_DIRTY", "GIT_RECORDED", "SIGNED")


@dataclass(frozen=True)
class ProvenanceObservation:
    """What the repository itself supports, and why."""

    level: str
    reason: str

    def caps(self, declared: str) -> str:
        """Return the declared level, lowered to what was observed."""

        if declared not in TRUST_LEVELS:
            return "LOCAL_UNTRUSTED"
        return declared if TRUST_LEVELS[declared] <= TRUST_LEVELS[self.level] else self.level


def _git(root: Path, *arguments: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, timeout=timeout, check=False)


def observe(repository_root: str | Path, paths: Iterable[str] = ()) -> ProvenanceObservation:
    """Report the highest provenance this checkout supports for these paths."""

    root = Path(repository_root)
    tracked = [path for path in paths]
    try:
        if _git(root, "rev-parse", "HEAD").returncode != 0:
            return ProvenanceObservation("LOCAL_UNTRUSTED", "no Git head to observe")
        if tracked:
            listed = _git(root, "ls-files", "--error-unmatch", "--", *tracked)
            if listed.returncode != 0:
                return ProvenanceObservation("LOCAL_UNTRUSTED", "an observed path is not tracked by Git")
        status = _git(root, "status", "--porcelain", "--", *tracked) if tracked else _git(root, "status", "--porcelain")
        if status.returncode != 0:
            return ProvenanceObservation("LOCAL_UNTRUSTED", "the working tree state could not be read")
        if status.stdout.strip():
            return ProvenanceObservation("GIT_DIRTY", "the observed paths differ from the commit")
        if _git(root, "verify-commit", "HEAD").returncode == 0:
            return ProvenanceObservation("SIGNED", "the head commit signature verifies")
        return ProvenanceObservation("GIT_RECORDED", "the observed paths are tracked and match the commit")
    except (OSError, subprocess.SubprocessError):
        return ProvenanceObservation("LOCAL_UNTRUSTED", "Git could not be executed")
