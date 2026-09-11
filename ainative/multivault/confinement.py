"""Result-path confinement for semantic and MCP responses (ADR-0015 section 9).

VaultProtocol v4 remains the owner of vault structure and write confinement;
this module composes the checks and consumes a caller-supplied confine
callable bound to the active vault and project. It never reimplements vault
path rules (ADR-0015 section 10).
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable


@dataclass(frozen=True)
class ConfinedResult:
    decision: str
    reason: str


@dataclass(frozen=True)
class ResultConfinement:
    session_project_security_id: str
    envelope_roots: tuple[str, ...]
    vault_confine: Callable[[str], bool]

    def admit(self, canonical_path: str, project_security_id: str) -> ConfinedResult:
        if not canonical_path or not os.path.isabs(canonical_path):
            return ConfinedResult("DENY", "result path is not canonical")
        if project_security_id != self.session_project_security_id:
            return ConfinedResult("DENY", "result belongs to another project security id")
        if not any(_within(root, canonical_path) for root in self.envelope_roots):
            return ConfinedResult("DENY", "result path is outside the allowed context envelope")
        if not self.vault_confine(canonical_path):
            return ConfinedResult("DENY", "result path is outside the VaultProtocol confinement")
        return ConfinedResult("ALLOW", "result confined to project, envelope and VaultProtocol")


def _within(root: str, path: str) -> bool:
    normalized_root = os.path.normcase(os.path.normpath(root))
    normalized_path = os.path.normcase(os.path.normpath(path))
    return normalized_path == normalized_root or normalized_path.startswith(normalized_root + os.sep)