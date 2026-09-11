"""Pure cross-domain canaries for MV-01."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class DomainCanary:
    source_domain: str
    requested_domain: str
    operation: str

def evaluate(canary: DomainCanary) -> dict[str, str]:
    """Cross-domain work is denied before any adapter, filesystem or network access."""
    if not canary.source_domain or not canary.requested_domain:
        return {"verdict": "DENY", "reason": "missing security domain"}
    if canary.source_domain != canary.requested_domain:
        return {"verdict": "DENY", "reason": "cross-domain request"}
    return {"verdict": "ALLOW", "reason": "same domain only"}
