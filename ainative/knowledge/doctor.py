"""Knowledge doctor section: measured status, honest degradation (Phase 15).

Composes the store, the review queue and the continuity owner. Optional
providers report ABSENT (degraded, never fatal); a corrupt store reports
FAIL; promotion mode and trust reflect the K5 STOP decision honestly
(GATE_CLOSED / UNVERIFIED). Read-only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import continuity as continuitylib
from . import errors as errorslib
from . import review as reviewlib
from . import store as storelib

STATUS_ABSENT = "ABSENT"
STATUS_OK = "OK"
STATUS_FAIL = "FAIL"
STALE_SIGNALS = ("POTENTIALLY_STALE", "STALE_UNRESOLVED")


def knowledge_status(project: Path) -> dict[str, Any]:
    """Measured Knowledge footprint for doctor. Reads only."""

    root = Path(project)
    state_dir = root / ".ai-native" / "state" / "knowledge"
    report: dict[str, Any] = {"status": STATUS_ABSENT, "store": str(state_dir),
                              "candidates": 0, "review_backlog": 0,
                              "conflicts": 0, "stale": 0,
                              "working": {"checkpoints": 0, "expired": 0},
                              "graph_provider": "ABSENT",
                              "semantic_provider": "ABSENT",
                              "multivault_scope": "UNSCOPED",
                              "promotion_mode": reviewlib.GATE_CLOSED,
                              "trust": reviewlib.UNVERIFIED}
    if not state_dir.is_dir():
        return report
    try:
        storage = storelib.storage_status(root)
        queue = reviewlib.review_queue(root)
        working = continuitylib.checkpoint_status(root)
    except (errorslib.KnowledgeError, OSError):
        return {"status": STATUS_FAIL, "store": str(state_dir),
                "detail": "knowledge store is corrupt or unreadable"}
    conflicts = sum(1 for item in queue["queue"]
                    if item["verdict"] in reviewlib.CONFLICT_VERDICTS)
    stale = sum(1 for item in queue["queue"]
                if item.get("staleness") in STALE_SIGNALS)
    graph_available = (root / "graphify-out" / "graph.json").is_file()
    bound = (root / ".ai-native" / "authority.json").is_file()
    report.update({"status": STATUS_OK, "storage": storage,
                   "candidates": queue["scanned"],
                   "review_backlog": len(queue["queue"]),
                   "conflicts": conflicts, "stale": stale,
                   "working": working,
                   "graph_provider": "AVAILABLE" if graph_available else "ABSENT",
                   "semantic_provider": "ABSENT",
                   "multivault_scope": "BOUND" if bound else "UNSCOPED"})
    return report
