"""Locate the distribution payload the installer copies from.

Three situations must all work, and they resolve in this order:

1. `AINATIVE_STACK_SOURCE` — an explicit override. The tests use it, and so does
   anyone running one checkout's CLI against another checkout's payload.
2. A repository checkout — the package sits inside the stack repo. Preferred
   over the staged payload so a developer always installs live sources.
3. A staged payload inside the installed package (`ainative/_payload/`), written
   at build time by `_build_backend.py`. This is what a user who ran
   `pip install ainative-dev-stack` on a machine with no checkout gets.

Anything else is `DISTRIBUTION_SOURCE_UNAVAILABLE`. Guessing a source is how an
installer ends up copying nothing and reporting success.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import LifecycleError
from .paths import validate_relative

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PAYLOAD_DIRNAME = "_payload"
SOURCE_ENV = "AINATIVE_STACK_SOURCE"

# Files that must exist for a directory to be a usable stack source. A checkout
# missing any of them would install a partial profile and call it done.
REQUIRED_MARKERS = ("AGENTS.md", "VERSION", "conventions.json", "skills", "tools/ai_docs")


@dataclass(frozen=True)
class DistributionSource:
    """A validated directory holding the files a profile installs."""

    root: Path
    origin: str          # "env" | "checkout" | "payload"
    version: str

    def path(self, relative: str) -> Path:
        """Resolve a manifest-declared source path inside the distribution."""

        parsed = validate_relative(relative)
        candidate = self.root.joinpath(*parsed.parts)
        try:
            candidate.resolve(strict=False).relative_to(self.root.resolve(strict=False))
        except ValueError:
            raise LifecycleError("PATH_ESCAPE",
                                 f"source {relative!r} leaves the distribution root") from None
        return candidate

    def to_record(self) -> dict:
        return {"root": str(self.root), "origin": self.origin, "version": self.version}


def read_version(root: Path) -> str:
    try:
        value = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return value or "0.0.0"


def _is_stack_root(candidate: Path) -> bool:
    return all((candidate / marker).exists() for marker in REQUIRED_MARKERS)


def _candidates() -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    override = os.environ.get(SOURCE_ENV)
    if override:
        found.append((Path(override).expanduser(), "env"))
    # The package lives at <stack>/ainative/ inside a checkout.
    found.append((PACKAGE_ROOT.parent, "checkout"))
    found.append((PACKAGE_ROOT / PAYLOAD_DIRNAME, "payload"))
    return found


def resolve() -> DistributionSource:
    """Return the first usable source, or refuse with what was tried."""

    tried: list[str] = []
    for candidate, origin in _candidates():
        try:
            root = candidate.resolve(strict=True)
        except OSError:
            tried.append(f"{origin}:{candidate} (absent)")
            continue
        if not _is_stack_root(root):
            missing = [m for m in REQUIRED_MARKERS if not (root / m).exists()]
            tried.append(f"{origin}:{root} (missing {', '.join(missing)})")
            continue
        return DistributionSource(root=root, origin=origin, version=read_version(root))

    raise LifecycleError(
        "DISTRIBUTION_SOURCE_UNAVAILABLE",
        "no usable AI Native distribution source found; "
        f"set {SOURCE_ENV} to a stack checkout. Tried: " + "; ".join(tried),
        tried=tried)


__all__ = ["DistributionSource", "resolve", "read_version", "PACKAGE_ROOT",
           "PAYLOAD_DIRNAME", "SOURCE_ENV", "REQUIRED_MARKERS"]
