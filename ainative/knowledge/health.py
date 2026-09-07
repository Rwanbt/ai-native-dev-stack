"""Read-only knowledge health for `status` and `doctor`. Never writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import store as storelib
from .errors import KnowledgeError

EMPTY = "empty"
HEALTHY = "healthy"
CORRUPTED = "corrupted"


@dataclass
class HealthReport:
    state: str = EMPTY
    candidates: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    audit_events: int = 0
    detail: str = "no knowledge store"

    def to_record(self) -> dict[str, Any]:
        return {"state": self.state, "candidates": self.candidates,
                "by_status": dict(self.by_status),
                "audit_events": self.audit_events, "detail": self.detail}

    def render(self) -> str:
        if self.state == EMPTY:
            return "knowledge: no candidates stored"
        if self.state == CORRUPTED:
            return f"knowledge: CORRUPTED — {self.detail}"
        parts = [f"{status} {count}" for status, count in sorted(self.by_status.items())]
        return (f"knowledge: {self.state} — {self.candidates} candidate(s) "
                f"({', '.join(parts)}), {self.audit_events} audit event(s)")


def build(project: Path) -> HealthReport:
    """Inspect the store. Read-only; corruption is reported, never raised."""

    if not storelib.candidates_path(project).is_file():
        return HealthReport()
    try:
        records = storelib.read_all(project)
    except KnowledgeError as error:
        return HealthReport(state=CORRUPTED, detail=str(error))
    try:
        events = storelib.read_audit(project)
    except KnowledgeError as error:
        return HealthReport(state=CORRUPTED, detail=str(error))
    by_status: dict[str, int] = {}
    for record in records:
        by_status[record["status"]] = by_status.get(record["status"], 0) + 1
    return HealthReport(state=HEALTHY, candidates=len(records),
                        by_status=by_status, audit_events=len(events),
                        detail="store readable")


__all__ = ["EMPTY", "HEALTHY", "CORRUPTED", "HealthReport", "build"]