"""Managed regions inside files the stack does not own.

`.gitignore` belongs to the project, not to us. Replacing it wholesale on
install and deleting it on uninstall would destroy whatever else the project
put there. So the stack writes a delimited region, remembers only that region,
and on removal takes back exactly those bytes — everything outside the markers
is preserved byte for byte.
"""

from __future__ import annotations

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

    def render(self) -> str:
        body = "\n".join([self.begin, *self.lines, self.end])
        return body + "\n"


def _split(text: str, spec: BlockSpec) -> tuple[str, str | None, str]:
    """Return (before, block, after). `block` is None when absent.

    Only the first block is recognised. A duplicate is left in `after` and
    reported by `doctor` rather than silently merged: two blocks mean something
    other than this code wrote one of them.
    """

    start = text.find(spec.begin)
    if start == -1:
        return text, None, ""
    stop = text.find(spec.end, start)
    if stop == -1:
        return text, None, ""
    stop_end = stop + len(spec.end)
    if stop_end < len(text) and text[stop_end] == "\n":
        stop_end += 1
    return text[:start], text[start:stop_end], text[stop_end:]


def read(path: Path, spec: BlockSpec) -> str | None:
    """The block currently present in the file, or None."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    _, block, _ = _split(text, spec)
    return block


def count(path: Path, spec: BlockSpec) -> int:
    try:
        return path.read_text(encoding="utf-8").count(spec.begin)
    except OSError:
        return 0


def apply(path: Path, spec: BlockSpec) -> tuple[str, bool]:
    """Return (new file content, changed?) with the block present and current.

    `apply` and `remove` are exact inverses: the block is appended with no
    inserted separator, so removing it later restores the original bytes. The
    one normalisation is a trailing newline on a file that lacked one — a text
    config file without a final newline is malformed, and appending a block to
    its last line would corrupt that line.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    before, block, after = _split(text, spec)
    rendered = spec.render()
    if block is not None:
        updated = before + rendered + after
    else:
        head = text if not text or text.endswith("\n") else text + "\n"
        updated = head + rendered
    return updated, updated != text


def remove(path: Path, spec: BlockSpec) -> tuple[str | None, bool]:
    """Return (new content, changed?). None means the file should be deleted.

    Deletion is proposed only when the managed block was the file's entire
    content — the stack created it and nobody added anything. Otherwise exactly
    the block's bytes are taken back and everything else is returned untouched.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, False
    before, block, after = _split(text, spec)
    if block is None:
        return text, False
    remaining = before + after
    if not remaining.strip():
        return None, True
    return remaining, True


__all__ = ["BlockSpec", "read", "count", "apply", "remove"]
