"""Repository-local plugin/MCP/config admission for sensitive harness sessions.

Repository content is untrusted (K0-B3): anything a checkout can make a harness
autoload is a security-relevant surface. The scan below inventories those
surfaces for reporting, but the sensitive decision is owned by harness adapter
evidence: an unknown disable capability denies TEAM/CONFIDENTIAL/CRITICAL
regardless of what the scan found. MV-00.4 reports `disable_control = UNKNOWN`,
so sensitive admission denies by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .capability import ControlLevel, Observation
from .schema import SecurityClassification


class SurfaceKind(str, Enum):
    MCP_CONFIG = "mcp_config"
    PLUGIN_CONFIG = "plugin_config"
    AGENT_CONFIG = "agent_config"
    COMMAND_CONFIG = "command_config"
    PROVIDER_OVERRIDE = "provider_override"
    ENVIRONMENT_HOOK = "environment_hook"


# The MV-00 probe (scripts/mv00/harness_autoload.py) inventories these names as
# evidence; this catalog is the admission contract and must stay a superset.
SURFACE_CATALOG: dict[str, SurfaceKind] = {
    ".mcp.json": SurfaceKind.MCP_CONFIG,
    "AGENTS.md": SurfaceKind.AGENT_CONFIG,
    "CLAUDE.md": SurfaceKind.AGENT_CONFIG,
    "GEMINI.md": SurfaceKind.AGENT_CONFIG,
    "mcp.json": SurfaceKind.MCP_CONFIG,
    "opencode.json": SurfaceKind.PLUGIN_CONFIG,
    "settings.json": SurfaceKind.ENVIRONMENT_HOOK,
    "settings.local.json": SurfaceKind.ENVIRONMENT_HOOK,
}


@dataclass(frozen=True)
class RepositorySurface:
    path: str
    kind: SurfaceKind


@dataclass(frozen=True)
class HarnessAutoloadAdapter:
    """Probe-backed declaration of what a harness lets a repository autoload.

    Trusted input: supplied by the launcher from probe evidence, never built
    from repository content.
    """

    harness: str
    harness_version: str
    adapter_version: str
    probe_version: str
    disable_control: ControlLevel
    observation: Observation
    evidence_digest: str

    def is_probe_backed(self) -> bool:
        return bool(
            self.harness
            and self.harness_version
            and self.adapter_version
            and self.probe_version
            and self.evidence_digest
            and self.disable_control is ControlLevel.VERIFIED
            and self.observation.is_bounded()
        )


@dataclass(frozen=True)
class RepositoryAdmission:
    decision: str
    reason: str


def scan_repository(root: Path) -> tuple[RepositorySurface, ...]:
    """Inventory recognized project-autoload surfaces; a name is evidence, not trust."""
    found = [
        RepositorySurface(path.relative_to(root).as_posix(), SURFACE_CATALOG[path.name])
        for path in root.rglob("*")
        if path.is_file() and path.name in SURFACE_CATALOG
    ]
    return tuple(sorted(found, key=lambda surface: surface.path))


def admit_repository(
    surfaces: tuple[RepositorySurface, ...],
    adapter: HarnessAutoloadAdapter | None,
    classification: SecurityClassification,
) -> RepositoryAdmission:
    """Fail closed: TEAM and above require exact probe-backed neutralization."""
    if classification is SecurityClassification.PERSONAL:
        return RepositoryAdmission(
            "ALLOW",
            f"personal classification records {len(surfaces)} surface(s) without neutralization proof",
        )
    if adapter is None:
        return RepositoryAdmission("DENY", "no harness adapter for the active harness")
    if not adapter.is_probe_backed():
        return RepositoryAdmission("DENY", f"{adapter.harness} project-autoload control is not probe-backed")
    return RepositoryAdmission(
        "ALLOW",
        f"{adapter.harness} neutralizes {len(surfaces)} project-autoload surface(s) with probe-backed evidence",
    )