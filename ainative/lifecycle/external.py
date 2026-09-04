"""Managed regions inside files the stack does not own.

`.gitignore` belongs to the project, not to us. Replacing it wholesale on
install and deleting it on uninstall would destroy whatever else the project
put there. So the stack writes a delimited region, remembers only that region,
and on removal takes back exactly those bytes — everything outside the markers
is preserved byte for byte.

"Byte for byte" is meant literally, and two things are needed for it. The file
is read with newline translation off, because Python's text mode turns `\r\n`
into `\n` and writing that back silently converts a CRLF file to LF
(EMP-LC-025). And the block is written with whatever line ending the file
already uses, so appending to a CRLF file does not leave it mixed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BEGIN_TEMPLATE = "{prefix} >>> BEGIN {marker} (managed — do not edit inside)"
END_TEMPLATE = "{prefix} <<< END {marker}"


@dataclass(frozen=True)
class BlockSpec:
    marker: str
    comment_prefix: str
    lines: tuple[str, ...]

    @property
    def begin(self) -> str:
        return BEGIN_TEMPLATE.format(prefix=self.comment_prefix, marker=self.marker)

    @property
    def end(self) -> str:
        return END_TEMPLATE.format(prefix=self.comment_prefix, marker=self.marker)

    def render(self, newline: str = "\n") -> str:
        return newline.join([self.begin, *self.lines, self.end]) + newline


def _newline_of(text: str) -> str:
    """The line ending the file already uses. CRLF wins when it appears at all."""

    return "\r\n" if "\r\n" in text else "\n"


def _openers(text: str, spec: BlockSpec) -> list[int]:
    """Offsets where the BEGIN marker starts its own line.

    Line-anchored, because a marker quoted inside a longer line is prose about
    the block, not the block.
    """

    return [match.start() for match in
            re.finditer(f"(?m)^{re.escape(spec.begin)}", text)]


def _split(text: str, spec: BlockSpec) -> tuple[str, str | None, str]:
    """Return (before, block, after). `block` is None when absent.

    A BEGIN whose matching END has another BEGIN in between is not an opener —
    it is text that merely looks like one. Accepting it made a `.gitignore`
    mentioning the marker in prose lose everything between that mention and the
    real block's END (EMP-LC-026).

    Only the first genuine block is recognised. A duplicate is left in `after`
    and reported by `doctor` rather than silently merged: two blocks mean
    something other than this code wrote one of them.
    """

    openers = _openers(text, spec)
    closer = re.compile(f"(?m)^{re.escape(spec.end)}")
    for index, start in enumerate(openers):
        # Line-anchored, like the opener. `find` matched an END quoted inside a
        # longer line, which truncated the region and left a marker fragment in
        # the user's file (EMP-LC-028).
        match = closer.search(text, start)
        if match is None:
            break
        stop = match.start()
        nested = [other for other in openers[index + 1:] if other < stop]
        if nested:
            continue                      # this BEGIN opens nothing
        stop_end = stop + len(spec.end)
        if text[stop_end:stop_end + 2] == "\r\n":
            stop_end += 2
        elif text[stop_end:stop_end + 1] == "\n":
            stop_end += 1
        return text[:start], text[start:stop_end], text[stop_end:]
    return text, None, ""


def read_raw(path: Path) -> str | None:
    """The file's text with no newline translation, or None when unreadable."""

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def read(path: Path, spec: BlockSpec) -> str | None:
    """The block currently present in the file, or None."""

    text = read_raw(path)
    if text is None:
        return None
    _, block, _ = _split(text, spec)
    return block


def count(path: Path, spec: BlockSpec) -> int:
    text = read_raw(path)
    return 0 if text is None else len(_openers(text, spec))


def apply(path: Path, spec: BlockSpec) -> tuple[str, bool]:
    """Return (new file content, changed?) with the block present and current.

    `apply` and `remove` are exact inverses: the block is appended with no
    inserted separator, so removing it later restores the original bytes. The
    one normalisation is a trailing newline on a file that lacked one —
    appending to its last line would corrupt that line.
    """

    text = read_raw(path) or ""
    newline = _newline_of(text)
    before, block, after = _split(text, spec)
    rendered = spec.render(newline)
    if block is not None:
        updated = before + rendered + after
    else:
        head = text if not text or text.endswith(("\n", "\r")) else text + newline
        updated = head + rendered
    return updated, updated != text


def remove(path: Path, spec: BlockSpec) -> tuple[str | None, bool]:
    """Return (new content, changed?). None means the file should be deleted.

    Deletion is proposed only when the managed block was the file's entire
    content — the stack created it and nobody added anything. Otherwise exactly
    the block's bytes are taken back and everything else is returned untouched.
    """

    text = read_raw(path)
    if text is None:
        return None, False
    before, block, after = _split(text, spec)
    if block is None:
        return text, False
    remaining = before + after
    if not remaining.strip():
        return None, True
    return remaining, True


__all__ = ["BlockSpec", "read", "read_raw", "count", "apply", "remove"]
