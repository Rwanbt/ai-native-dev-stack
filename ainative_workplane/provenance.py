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
    # Reported, never required: which identities Git verified behind the
    # observed objects. A reviewer reading a refusal should be able to see who
    # signed rather than only that it was the wrong person.
    signers: tuple[str, ...] = ()

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


# Git prints the verification status, the signing key fingerprint and the key
# id. The fingerprint is the identity: it is what a project can authorize in
# advance, and it is the same field for GPG and SSH signing.
_SIGNATURE_FIELDS = "%G?\x1f%GF\x1f%GK"
_VERIFIED = "G"


def _signature_of(root: Path, path: str | None = None) -> str | None:
    """Return the signing identity behind one object, or None if there is none.

    WHY per path and not per path *set*: `git log -1 -- a b` reports the most
    recent commit touching *either*, so one signed commit made an entire set
    look signed while another path's content came from an unsigned one. The
    fourth-round implementation had exactly that bug (A99).
    """

    arguments = ["log", "-1", f"--format={_SIGNATURE_FIELDS}", *(["--", path] if path else [])]
    try:
        result = _git(root, *arguments)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    fields = result.stdout.strip().split("\x1f")
    if len(fields) != 3 or fields[0] != _VERIFIED:
        return None
    # The fingerprint, or the key id where the signing format supplies no
    # fingerprint. Empty means Git verified something it cannot name, which is
    # not an identity and therefore not an authorization.
    return fields[1] or fields[2] or None


def commit_count(target: str | Path, path: str) -> int:
    """How many commits have touched one path. -1 when Git cannot say.

    Used to establish that an object has never been rewritten, which is the
    only way an artifact can authorize itself without circularity: a file that
    has one commit still says what its author said.
    """

    try:
        result = _git(Path(target), "log", "--format=%H", "--", path)
    except (OSError, subprocess.SubprocessError):
        return -1
    if result.returncode != 0:
        return -1
    return len([line for line in result.stdout.splitlines() if line.strip()])


def signature_signers(target: str | Path, paths: Iterable[str] = ()) -> dict[str, str | None]:
    """The verified signing identity behind each observed path.

    @contract One entry per path, and a path whose last commit is unsigned or
    fails verification contributes None. A caller requiring a signature over a
    set must therefore find no None -- never one signed commit standing in for
    the rest.
    """

    root = Path(target)
    named = list(paths)
    if not named:
        return {"": _signature_of(root)}
    return {path: _signature_of(root, path) for path in named}


def signature_verified(target: str | Path, paths: Iterable[str] = (), *, authorized_signers: Iterable[str] | None = None) -> bool:
    """Whether every observed path was last written by an authorized signer.

    Two properties, deliberately separate, because the fifth review found the
    second one missing:

    - *cryptographic validity*, which Git decides: `%G?` is `G` only when the
      signature verifies against the configured keyring or allowed-signers
      file. An actor without a key cannot make it say `G`;
    - *authorization*, which Git cannot decide: a repository may accept several
      signing identities, and being able to sign ordinary commits is not being
      allowed to approve a policy change. The identity must appear in the set
      the project pinned in advance.

    `authorized_signers=None` establishes nothing. Where no set is pinned there
    is nobody to have authorized anything, and the answer is False rather than
    "any valid signature".
    """

    if authorized_signers is None:
        return False
    allowed = frozenset(authorized_signers)
    if not allowed:
        return False
    signers = signature_signers(target, paths)
    return bool(signers) and all(identity in allowed for identity in signers.values())


def observe(target: str | Path, paths: Iterable[str] = (), *, authorized_signers: Iterable[str] | None = None) -> ProvenanceFacts:
    """Establish what a checkout supports for the given paths.

    `git_reviewed` and `ci_verified` are never set here. They assert that a
    process happened, which a checkout cannot show, and this build ships no
    verifier for either. A policy requiring one fails closed — a real
    functional limit, stated rather than quietly approximated.

    `signature_verified` needs `authorized_signers`, the identities the project
    pinned. Without them a valid signature by anyone at all would satisfy a
    policy asking for approval, which is not what it asks.
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
        identities = signature_signers(root, named)
        signed = signature_verified(root, named, authorized_signers=authorized_signers)
        return ProvenanceFacts(
            git_recorded=True,
            signature_verified=signed,
            local_dirty=False,
            reason="tracked and matching the commit" + (", signed by an authorized identity" if signed else ""),
            signers=tuple(sorted({identity for identity in identities.values() if identity})),
        )
    except (OSError, subprocess.SubprocessError):
        return ProvenanceFacts(reason="Git could not be executed")


def observe_artifacts(paths: Iterable[str | Path], *, authorized_signers: Iterable[str] | None = None) -> ProvenanceFacts:
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
    return observe(base, relative, authorized_signers=authorized_signers)


def observe_artifact(path: str | Path, *, authorized_signers: Iterable[str] | None = None) -> ProvenanceFacts:
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
    return observe(base, [relative], authorized_signers=authorized_signers)
