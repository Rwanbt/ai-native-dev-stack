"""AI Native Dev Stack — Knowledge Lifecycle (B1-conformant foundation).

PR2 scope: schemas, identity grammar, assertion hashing, state machine,
durable-control envelope. No persistence, no CLI, no promotion path.
This package MUST NOT import `ainative_workplane/` (ADR-0011, reaffirmed
by K0-B3 S9: consume authority only through explicit injection points,
never by import or duplication).
"""

from __future__ import annotations

SCHEMA_VERSION = 1

__all__ = ["SCHEMA_VERSION"]
