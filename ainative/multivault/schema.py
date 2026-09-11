"""Canonical, descriptive Multi-Vault identities and digests for MV-02."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any

SCHEMA_VERSION = 1

def canonical_json(value: Any) -> bytes:
    """Stable JSON encoding: sorted keys, compact separators, no host repr()."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

def digest(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()

@dataclass(frozen=True)
class SecurityDomain:
    security_domain_id: str
    vault_logical_id: str
    project_security_id: str
    operator_authority_domain_id: str

    def identity_digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})

@dataclass(frozen=True)
class SecurityEpoch:
    security_domain_id: str
    epoch_counter_or_nonce: str
    authority_instance_generation: str

    def digest(self) -> str:
        return digest({"schema_version": SCHEMA_VERSION, **asdict(self)})

def policy_digest(policy: dict[str, Any]) -> str:
    """Policy callers supply the full normalized object; subsets are not accepted here."""
    return digest({"schema_version": SCHEMA_VERSION, "policy": policy})
