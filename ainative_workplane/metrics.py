"""Small deterministic metrics record used by pilot reporting."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path


@dataclass(frozen=True)
class PilotMetrics:
    setup_time_ms: int = 0
    verification_runtime_ms: int = 0
    convergence_runtime_ms: int = 0
    reruns: int = 0
    human_interventions: int = 0
    true_positive_gaps: int = 0
    false_positive_gaps: int = 0
    bugs_missed: int = 0
    state_conflicts: int = 0
    stale_invalidations: int = 0
    hotfix_friction: int = 0

    def write(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")), encoding="utf-8")
