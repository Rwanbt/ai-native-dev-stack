"""AI Native Dev Stack — Knowledge Lifecycle engine (Phase K1).

Lifecycle-side context and memory. This package MUST NOT import
`ainative_workplane/` (ADR-0011 section 2): Standard installs never load
an authority module, and knowledge supplies read-only context, never
verdicts. Work-plane evidence arrives only as caller-supplied serialized
records. See `docs/KNOWLEDGE-ARCHITECTURE.md` and ADR-0011.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

__all__ = ["SCHEMA_VERSION"]