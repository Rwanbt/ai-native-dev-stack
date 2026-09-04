"""SemVer comparison, done properly, with no dependency.

`"1.10.0" > "1.9.0"` is False as a string comparison and True as a version
comparison. An updater that gets this wrong offers a downgrade as an upgrade, so
the parsing is explicit and a value that does not parse is refused rather than
silently ordered as text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Major.minor.patch with an optional pre-release and build metadata, per
# semver.org. Build metadata is parsed and ignored for ordering, as the spec
# requires.
_PATTERN = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple = ()
    raw: str = ""

    def _key(self) -> tuple:
        # A release outranks any pre-release of the same triple, so an empty
        # pre-release sorts last: (1, ) beats (0, identifiers...).
        if not self.pre:
            return (self.major, self.minor, self.patch, 1, ())
        return (self.major, self.minor, self.patch, 0, self.pre)

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __le__(self, other: "Version") -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: "Version") -> bool:
        return self._key() > other._key()

    def __ge__(self, other: "Version") -> bool:
        return self._key() >= other._key()

    def __str__(self) -> str:
        return self.raw or f"{self.major}.{self.minor}.{self.patch}"


def parse(value: str) -> Version | None:
    """A Version, or None when `value` is not SemVer. Never guesses."""

    if not isinstance(value, str):
        return None
    match = _PATTERN.match(value.strip())
    if match is None:
        return None
    identifiers = []
    for item in (match.group("pre") or "").split(".") if match.group("pre") else []:
        identifiers.append((0, int(item), "") if item.isdigit() else (1, 0, item))
    return Version(int(match.group("major")), int(match.group("minor")),
                   int(match.group("patch")), tuple(identifiers), value.strip().lstrip("v"))


def is_newer(candidate: str, current: str) -> bool:
    """True only when both parse and `candidate` is strictly greater."""

    left, right = parse(candidate), parse(current)
    if left is None or right is None:
        return False
    return left > right


def compare(left: str, right: str) -> int | None:
    a, b = parse(left), parse(right)
    if a is None or b is None:
        return None
    return (a > b) - (a < b)


__all__ = ["Version", "parse", "is_newer", "compare"]
