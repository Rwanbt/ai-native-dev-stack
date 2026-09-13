"""Inspect and repair the recorded machine integration.

Split from `machine.py` so each module owns one responsibility: `machine.py`
owns the manifest record and its reversal; this module owns the read-only
health scan and the repair pass. Both read the same fields, and repair never
guesses beyond them.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import machine
from .machine import (PROBLEM_STATES, STATE_DRIFTED, STATE_MALFORMED,
                      STATE_MISSING, STATE_MODIFIED, STATE_OK, STATE_UNKNOWN,
                      METHOD_BEGIN, VAULT_BEGIN, _asset_path, _create_link,
                      _digest_bytes, _relative, digest_file, load,
                      manifest_path, method_block_text, vault_block_text)


def _link_state(target: Path, source: Path) -> tuple[str, str]:
    if not target.exists() and not target.is_symlink():
        return STATE_MISSING, ""
    try:
        resolved = target.resolve()
    except OSError as error:
        return STATE_UNKNOWN, f"cannot resolve: {error}"
    if resolved == source:
        return STATE_OK, ""
    return STATE_DRIFTED, f"points at {resolved}, not {source}"


def _render_state(target: Path, recorded: str | None) -> tuple[str, str]:
    if not target.is_file():
        return STATE_MISSING, ""
    current = digest_file(target)
    if recorded and current == recorded:
        return STATE_OK, ""
    return STATE_MODIFIED, "the file no longer matches what this stack wrote"


def _block_state(target: Path, begin: str, end: str) -> tuple[str, str]:
    if not target.is_file():
        return STATE_MISSING, "file absent"
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return STATE_UNKNOWN, f"cannot read: {error}"
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        return STATE_MISSING, "markers absent"
    if begin_count != 1 or end_count != 1:
        return STATE_MALFORMED, f"{begin_count} BEGIN marker(s), {end_count} END marker(s)"
    return STATE_OK, ""


def asset_state(home: Path, asset: dict) -> tuple[str, str]:
    """Classify one recorded asset against the machine as it is now."""

    target = _asset_path(home, asset)
    if target is None:
        return STATE_UNKNOWN, "record has no usable path"
    kind = asset.get("kind")
    if kind == "link":
        return _link_state(target, Path(str(asset.get("source", ""))))
    if kind == "rendered":
        return _render_state(target, asset.get("digest"))
    if kind == "block":
        return _block_state(target, str(asset.get("begin", "")),
                            str(asset.get("end", "")))
    return STATE_UNKNOWN, f"unknown asset kind {kind!r}"


def status(home: Path) -> dict:
    """Report the machine integration as it is now. Never writes, never guesses.

    An absent manifest is not a problem: it means this machine was never
    integrated. An unreadable manifest raises — fail closed.
    """

    home = Path(home)
    manifest = load(home)
    if manifest is None:
        return {"manifest": None, "present": False, "schema_version": None,
                "stack_version": None, "assets": [], "counts": {},
                "healthy": True,
                "detail": "no machine manifest: this machine has no recorded AI Native integration"}

    assets: list[dict] = []
    counts: dict[str, int] = {}
    for asset in manifest["assets"]:
        state, detail = asset_state(home, asset)
        counts[state] = counts.get(state, 0) + 1
        assets.append({"path": asset.get("path"), "kind": asset.get("kind"),
                       "state": state, "detail": detail})
    healthy = not any(counts.get(state) for state in PROBLEM_STATES)
    return {"manifest": str(manifest_path(home)), "present": True,
            "schema_version": manifest.get("schema_version"),
            "stack_version": manifest.get("stack_version"),
            "assets": sorted(assets, key=lambda item: str(item.get("path"))),
            "counts": counts, "healthy": healthy, "detail": ""}


def _template_reference(stack_root: Path | None, template) -> tuple[Path | None, str]:
    """Resolve a recorded template to a path, preferring the recorded root."""

    if not isinstance(template, str) or not template:
        return None, "no template recorded by an older schema"
    candidate = Path(template)
    if not candidate.is_absolute() and stack_root is not None:
        candidate = stack_root / candidate
    if not candidate.is_file():
        return None, f"template is no longer present: {candidate}"
    return candidate, ""


def _render_bytes(template: Path, stack_root: Path) -> bytes:
    wanted = template.read_text(encoding="utf-8")
    wanted = wanted.replace("{{STACK_ROOT_JSON}}", json.dumps(str(stack_root)))
    wanted = wanted.replace("{{STACK_ROOT}}", str(stack_root))
    return wanted.encode("utf-8")

def repair(home: Path, *, dry_run: bool = False) -> dict:
    """Re-create what the manifest proves this stack installed, and only that.

    Links are re-created from the recorded source, rendered files from the
    recorded template (and only when the re-render still matches the recorded
    digest), blocks from the recorded heading or vault pair. Anything the user
    modified, retargeted or malformed is preserved and reported, never
    overwritten; a record that cannot be rebuilt is unrepairable, not guessed.
    """

    home = Path(home)
    manifest = load(home)
    if manifest is None:
        return {"operation": "machine repair", "dry_run": dry_run,
                "repaired": [], "unrepairable": [], "preserved": [],
                "detail": "no machine manifest: nothing is recorded as ours"}

    raw_root = manifest.get("stack_root")
    stack_root = Path(raw_root) if isinstance(raw_root, str) and raw_root else None
    repaired: list[str] = []
    unrepairable: list[dict] = []
    preserved: list[dict] = []
    for asset in manifest["assets"]:
        target = _asset_path(home, asset)
        relative = _relative(home, target) if target is not None else str(asset.get("path"))
        if target is None:
            unrepairable.append({"path": relative, "detail": "record has no usable path"})
            continue
        state, detail = asset_state(home, asset)
        kind = asset.get("kind")
        if state == STATE_OK:
            continue
        if state != STATE_MISSING:
            preserved.append({"path": relative, "state": state, "detail": detail})
            continue

        if kind == "link":
            source = Path(str(asset.get("source", "")))
            if not source.exists() and not source.is_symlink():
                unrepairable.append({"path": relative,
                                     "detail": f"the recorded source is gone: {source}"})
                continue
            if dry_run:
                repaired.append(relative)
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                ok, why = _create_link(source, target)
            except OSError as error:
                ok, why = False, str(error)
            (repaired.append(relative) if ok
             else unrepairable.append({"path": relative, "detail": why}))
            continue

        if kind == "rendered":
            if stack_root is None:
                unrepairable.append({"path": relative,
                                     "detail": "manifest recorded no stack root"})
                continue
            template, why = _template_reference(stack_root, asset.get("template"))
            if template is None:
                unrepairable.append({"path": relative, "detail": why})
                continue
            payload = _render_bytes(template, stack_root)
            recorded = asset.get("digest")
            if recorded and _digest_bytes(payload) != recorded:
                unrepairable.append(
                    {"path": relative,
                     "detail": "the distribution's template no longer produces the "
                               "recorded digest; refusing to write a different file"})
                continue
            if dry_run:
                repaired.append(relative)
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                repaired.append(relative)
            except OSError as error:
                unrepairable.append({"path": relative, "detail": str(error)})
            continue

        if kind == "block":
            if stack_root is None:
                unrepairable.append({"path": relative,
                                     "detail": "manifest recorded no stack root"})
                continue
            begin = str(asset.get("begin", ""))
            end = str(asset.get("end", ""))
            if begin == METHOD_BEGIN and asset.get("label") == "method block":
                heading = asset.get("heading")
                if not isinstance(heading, str) or not heading:
                    unrepairable.append({"path": relative,
                                         "detail": "no heading recorded by an older schema"})
                    continue
                block = method_block_text(stack_root, heading)
            elif begin == VAULT_BEGIN and asset.get("label") == "vault block":
                vault, slug = asset.get("vault"), asset.get("slug")
                if not isinstance(vault, str) or not isinstance(slug, str):
                    unrepairable.append({"path": relative,
                                         "detail": "vault pair not recorded by an older schema"})
                    continue
                block = vault_block_text(Path(vault), slug)
            else:
                unrepairable.append({"path": relative,
                                     "detail": f"unrecognized block record {begin!r}"})
                continue
            if dry_run:
                repaired.append(relative)
                continue
            try:
                current = target.read_text(encoding="utf-8") if target.is_file() else ""
                preamble = asset.get("preamble")
                if not current and isinstance(preamble, str) and preamble:
                    current = preamble.rstrip() + "\n"
                separator = "\n\n" if current.strip() else ""
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(current.rstrip() + separator + block + "\n",
                                  encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                unrepairable.append({"path": relative, "detail": str(error)})
                continue
            if _block_state(target, begin, end)[0] == STATE_OK:
                repaired.append(relative)
            else:
                unrepairable.append({"path": relative,
                                     "detail": "the block did not verify after the write"})
            continue

        unrepairable.append({"path": relative, "detail": f"cannot repair kind {kind!r}"})

    record = {"operation": "machine repair", "dry_run": dry_run,
              "repaired": sorted(repaired), "unrepairable": unrepairable,
              "preserved": preserved}
    if not dry_run:
        record["status"] = status(home)
    return record


__all__ = ["STATE_OK", "STATE_MISSING", "STATE_MODIFIED", "STATE_DRIFTED",
           "STATE_MALFORMED", "STATE_UNKNOWN", "PROBLEM_STATES",
           "asset_state", "status", "repair"]
