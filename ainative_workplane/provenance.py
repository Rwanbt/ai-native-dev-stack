"""Observe what is actually established about an object, as separate facts.

Two mistakes this module exists to prevent.

The first is treating a declaration as its own proof: an artifact saying
`"SIGNED"` is not a signature, and one saying `"GIT_REVIEWED"` is not a review.
So nothing here reads a claim — it looks at the object.

The second is ranking those properties on one scale. A signature verifies a
signature. It does not show that a human reviewed anything, and it does not
show that CI ran. Under a numeric order where SIGNED outranks CI_APPROVED, a
signed commit satisfies a policy that demanded CI, which is simply false. Facts
are therefore independent booleans, and a policy states the ones it needs.

Observation is also per object, not per repository. A clean source checkout
says something about the source; it says nothing about a work directory, an
approval root or a waiver that lives somewhere else. `observe` takes the paths
whose provenance is in question.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

# Every property the runtime can establish for itself. A policy may require any
# subset; it may never require something absent from this list, because nothing
# would be able to establish it.
OBSERVABLE_FACTS = ("git_recorded", "git_reviewed", "ci_verified", "signature_verified")


@dataclass(frozen=True)
class ProvenanceFacts:
    """What is established about one object, and what plainly is not."""

    git_recorded: bool = False
    git_reviewed: bool = False
    ci_verified: bool = False
    signature_verified: bool = False
    local_dirty: bool = True
    reason: str = "not observed"

    def unmet(self, required: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the required facts this object does not support."""

        missing = []
        for name, needed in sorted(required.items()):
            if not needed:
                continue
            if not getattr(self, name, False):
                missing.append(name)
        return tuple(missing)

    def satisfies(self, required: Mapping[str, Any]) -> bool:
        return not self.unmet(required)

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


UNOBSERVED = ProvenanceFacts()


def _git(root: Path, *arguments: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, timeout=timeout, check=False)


def signature_verified(target: str | Path, paths: Iterable[str] = ()) -> bool:
    """Whether Git verifies the signature on the commit that last wrote these paths.

    WHY the last commit touching the paths and not HEAD: the question is who
    signed *this object*. A signed head commit says nothing about a file
    someone else committed ten commits ago, and a policy asking for a signature
    on an approval is asking about the approval.

    Git decides, not this module: `%G?` is `G` only when the signature verifies
    against the configured keyring or allowed-signers file. An actor without
    the key cannot make it say `G`, which is what makes `signature` the one
    predicate an agent with commit rights cannot satisfy for itself.
    """

    root = Path(target)
    named = list(paths)
    arguments = ["log", "-1", "--format=%G?", *(["--", *named] if named else [])]
    try:
        result = _git(root, *arguments)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "G"


def observe(target: str | Path, paths: Iterable[str] = ()) -> ProvenanceFacts:
    """Establish what a checkout supports for the given paths.

    `git_reviewed` and `ci_verified` are never set here. They assert that a
    process happened, which a checkout cannot show, and this build ships no
    verifier for either. A policy requiring one fails closed — a real
    functional limit, stated rather than quietly approximated.
    """

    root = Path(target)
    named = list(paths)
    try:
        if _git(root, "rev-parse", "HEAD").returncode != 0:
            return ProvenanceFacts(reason="no Git head to observe")
        if named and _git(root, "ls-files", "--error-unmatch", "--", *named).returncode != 0:
            return ProvenanceFacts(reason="an observed path is not tracked by Git")
        status = _git(root, "status", "--porcelain", "--", *named) if named else _git(root, "status", "--porcelain")
        if status.returncode != 0:
            return ProvenanceFacts(reason="the working tree state could not be read")
        if status.stdout.strip():
            return ProvenanceFacts(reason="the observed paths differ from the commit")
        signed = signature_verified(root, named)
        return ProvenanceFacts(
            git_recorded=True,
            signature_verified=signed,
            local_dirty=False,
            reason="tracked and matching the commit" + (", and its last commit is signed" if signed else ""),
        )
    except (OSError, subprocess.SubprocessError):
        return ProvenanceFacts(reason="Git could not be executed")


def observe_artifacts(paths: Iterable[str | Path]) -> ProvenanceFacts:
    """Establish what is known about a specific set of files.

    Only the objects named here are observed. An audit trail sitting beside
    them is not authority and must not decide whether they are clean.
    """

    targets = [Path(path) for path in paths]
    if not targets:
        return ProvenanceFacts(reason="no authority artifact to observe")
    try:
        toplevel = _git(targets[0].parent, "rev-parse", "--show-toplevel")
        if toplevel.returncode != 0 or not toplevel.stdout.strip():
            return ProvenanceFacts(reason="the authority artifacts are not inside a Git work tree")
    except (OSError, subprocess.SubprocessError):
        return ProvenanceFacts(reason="Git could not be executed")
    base = Path(toplevel.stdout.strip())
    relative = []
    for target in targets:
        try:
            relative.append(target.resolve().relative_to(base.resolve()).as_posix())
        except ValueError:
            return ProvenanceFacts(reason=f"{target.name} is outside its own work tree")
    return observe(base, relative)


def observe_artifact(path: str | Path) -> ProvenanceFacts:
    """Establish what is known about the file or directory holding an artifact.

    An artifact outside any repository inherits nothing from the repository it
    happens to describe. This is what stops a work directory in /tmp from
    borrowing the cleanliness of the checkout it points at.
    """

    target = Path(path)
    root = target if target.is_dir() else target.parent
    try:
        toplevel = _git(root, "rev-parse", "--show-toplevel")
        if toplevel.returncode != 0 or not toplevel.stdout.strip():
            return ProvenanceFacts(reason=f"{target.name} is not inside a Git work tree")
    except (OSError, subprocess.SubprocessError):
        return ProvenanceFacts(reason="Git could not be executed")
    base = Path(toplevel.stdout.strip())
    try:
        relative = target.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return ProvenanceFacts(reason=f"{target.name} is outside its own work tree")
    return observe(base, [relative])
