"""Qualification and doctor display rules (Multi-Vault plan section 20).

Bare ENFORCED is never a valid label; unknown qualification is displayed as
UNKNOWN and never as a stronger claim. Doctor checks are fail-closed: their
absence or failure can never render as PASS.
"""
from __future__ import annotations

from dataclasses import dataclass

DISPLAYABLE_QUALIFICATIONS = ("UNKNOWN", "GUARDED", "ENFORCED-DIAGNOSTIC", "ENFORCED-AUTHENTICATED")
CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_UNKNOWN = "UNKNOWN"


def qualification_label(level: str) -> str:
    if level == "ENFORCED":
        raise ValueError("bare ENFORCED is not a valid qualification label")
    if level not in DISPLAYABLE_QUALIFICATIONS:
        raise ValueError("unsupported qualification label")
    return level


@dataclass(frozen=True)
class ContextReport:
    security_domain_id: str
    classification: str
    vault_identity: str
    checkout_identity: str
    harness: str
    provider_class: str
    model: str
    routing: str
    qualification: str
    observation_windows: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]
    supported: bool

    def render(self) -> str:
        lines = [
            f"security_domain: {self.security_domain_id}",
            f"classification: {self.classification}",
            f"vault_identity: {self.vault_identity}",
            f"checkout_identity: {self.checkout_identity}",
            f"harness: {self.harness}",
            f"provider_class: {self.provider_class}",
            f"model: {self.model}",
            f"routing: {self.routing}",
            f"qualification: {qualification_label(self.qualification)}",
            f"observation_windows: {', '.join(self.observation_windows) or 'none'}",
            f"unsupported_capabilities: {', '.join(self.unsupported_capabilities) or 'none'}",
            f"supported: {'yes' if self.supported else 'no'}",
        ]
        return "\n".join(lines)


def doctor_check(value: bool | None, *, fresh: bool = True) -> str:
    """Fail closed: only an explicit True (and fresh) renders as PASS."""
    if value is None:
        return CHECK_UNKNOWN
    if value and fresh:
        return CHECK_PASS
    return CHECK_FAIL


def doctor_report(checks: dict[str, bool | None]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((name, doctor_check(value)) for name, value in checks.items()))