#!/usr/bin/env python3
"""finding_common.py — Shared helpers for deterministic finding identity.

A finding's identity must be STABLE across scans: the same physical issue
(same kind, same place) must always produce the same id. Random UUIDs break
deduplication, the Knowledge Graph (which would accumulate a new Debt node per
scan), history tracking, decay and calibration.

The fingerprint is derived from (category, subcategory, file, line,
discriminator). The discriminator disambiguates findings that would otherwise
collide on the first four (e.g. two lint codes on the same line, a duplication
group keyed by its AST hash). Pass the most stable key available — a rule code,
a function name, or an AST hash — never a value that changes on every edit
(like a metric count).
"""
from __future__ import annotations

import hashlib


def finding_id(
    category: str,
    subcategory: str,
    file: str = "",
    line: str = "",
    discriminator: str = "",
) -> str:
    """Return a deterministic finding id of the form 'f-<16 hex>'.

    Stable for a given (category, subcategory, file, line, discriminator):
    re-scanning unchanged code yields the same id, so dedup/KG/history work.
    """
    raw = f"{category}|{subcategory}|{file}|{line}|{discriminator}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"f-{digest}"
