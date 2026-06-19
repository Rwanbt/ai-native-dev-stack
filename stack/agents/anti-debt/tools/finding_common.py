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
import re

# Centralized secret-detection patterns — shared by the Python heuristic scanner
# (heuristic_scan.py) AND the Rust/JS polyglot scanner so a new pattern is added
# ONCE and every scanner gets it. Provider-specific patterns first; the generic
# high-entropy pattern is last so provider labels win for real keys.
SECRET_PATTERNS = [
    (re.compile(r'sk_live_[A-Za-z0-9]{20,}'), "Stripe live secret key"),
    (re.compile(r'sk_test_[A-Za-z0-9]{20,}'), "Stripe test secret key"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS access key ID"),
    (re.compile(r'AIza[0-9A-Za-z\-_]{35}'), "Google API key"),
    (re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}'), "GitHub token"),
    (re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}'), "Slack token"),
    (re.compile(r'-----BEGIN [A-Z ]+PRIVATE KEY-----'), "Private key"),
    (re.compile(r'(?i)(?:api[_-]?key|secret|token|passwd|password|access[_-]?key|client[_-]?secret)\s*[:=]\s*["\'][A-Za-z0-9+/_\-]{16,}["\']'), "generic credential"),
]


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
